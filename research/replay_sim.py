"""Replay simulator — drive the REAL paper loop over REAL cached candles.

The 30-day paper run is the evidence the live gate rests on, and until it
starts, most of that machinery has only ever been exercised by unit tests
against fakes. This replays recorded market data through the actual
`PaperTrader`, one tick at a time, so the strategy, risk engine, cost model,
fill simulator and session store all run the exact path the live-ish run will.

**What it is for:** proving the trade lifecycle works end to end, and showing
which branches real data actually reaches. `tradecc backtest` answers "would
this have made money"; this answers "does the machinery that will make the
trades work, and which parts has real data never touched".

**What it is NOT for:** deciding whether a strategy has an edge. It reports
lifecycle coverage first and P&L last, deliberately. Trade count here is a
*coverage* measure — how much of the machinery got exercised — and reading it
as a signal, or tuning parameters until it rises, is the selection bias every
protocol in this repo exists to prevent. Edge questions go through
`research/walk_forward.py` and the pre-registration protocol, not this file.

Deterministic: no network, no clock, no randomness. The same cache produces
the same result every run, so a change in the output is a change in the code.

    PYTHONPATH=src .venv/bin/python research/replay_sim.py
    PYTHONPATH=src .venv/bin/python research/replay_sim.py --interval 1h --warmup 60
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from pathlib import Path
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from core.candles import Candle  # noqa: E402
from core.config import (  # noqa: E402
    BacktestConfig,
    DataConfig,
    PaperConfig,
    RiskConfig,
    RunConfig,
    StrategyConfig,
)
from core.types import Mode  # noqa: E402
from execution.mock import MockQuoteSource  # noqa: E402
from paper.session import PaperSessionStore  # noqa: E402
from paper.trader import PaperTrader  # noqa: E402
from strategy.registry import build_strategy  # noqa: E402

CACHE = ROOT / "research" / ".candle-cache"
SOL = "So11111111111111111111111111111111111111112"


def load_cached(pool: str, interval: str) -> list[Candle]:
    path = CACHE / f"{pool}_{interval}.json"
    if not path.is_file():
        raise SystemExit(
            f"no cached candles at {path}\n"
            "Populate the cache first with: tradecc backtest --refresh"
        )
    rows = json.loads(path.read_text())
    return [
        Candle(
            timestamp=datetime.fromisoformat(r["t"]),
            open=Decimal(r["o"]),
            high=Decimal(r["h"]),
            low=Decimal(r["l"]),
            close=Decimal(r["c"]),
            volume=Decimal(r["v"]),
        )
        for r in rows
    ]


class ReplayCandleSource:
    """Serves a growing prefix of recorded history, newest bar last.

    This is the whole point-in-time discipline of the simulator: at tick `i`
    the trader can see bars 0..i and nothing after. A source that handed over
    the full series would let the strategy read its own future, and the result
    would be a lookahead artefact rather than a replay.
    """

    def __init__(self, candles: list[Candle], warmup: int) -> None:
        self._candles = candles
        self._cursor = warmup

    @property
    def exhausted(self) -> bool:
        return self._cursor >= len(self._candles)

    @property
    def now(self) -> datetime:
        return self._candles[min(self._cursor, len(self._candles) - 1)].timestamp

    def advance(self) -> None:
        self._cursor += 1

    def fetch_candles(self, pool_address: str, interval: str = "", limit: int = 0) -> list[Candle]:
        window = self._candles[: self._cursor + 1]
        return window[-limit:] if limit else window


@dataclass
class Coverage:
    """What the run actually exercised, which is the primary output."""

    actions: Counter = field(default_factory=Counter)
    exit_reasons: Counter = field(default_factory=Counter)
    block_reasons: Counter = field(default_factory=Counter)
    errors: Counter = field(default_factory=Counter)

    def record(self, result) -> None:
        self.actions[result.action] += 1
        if result.trade is not None:
            self.exit_reasons[result.trade.exit_reason] += 1
        if result.action == "entry_blocked" and result.detail:
            self.block_reasons[result.detail.split(":")[0][:60]] += 1
        if result.error:
            self.errors[result.error.split(":")[0][:40]] += 1


def simulate(pool: str, interval: str, warmup: int, quote_slippage: str) -> tuple:
    candles = load_cached(pool, interval)
    if len(candles) <= warmup:
        raise SystemExit(f"only {len(candles)} cached bars, need more than warmup={warmup}")

    workdir = Path(tempfile.mkdtemp(prefix="replay-sim-"))
    config = RunConfig(
        mode=Mode.PAPER,
        risk=RiskConfig(),
        strategy=StrategyConfig(name="momentum", token_mints=(SOL,)),
        data=DataConfig(candle_interval=interval),
        paper=PaperConfig(pool_address=pool),
        backtest=BacktestConfig(),
        state_dir=workdir / "state",
        gate_file=workdir / "live-gate.json",
    )
    source = ReplayCandleSource(candles, warmup)
    store = PaperSessionStore(config.state_dir)
    trader = PaperTrader(
        config=config,
        strategy=build_strategy(config.strategy),
        # A deterministic quote source priced off the bar being replayed: the
        # real one needs the network, and recorded history carries no quotes.
        # It models side correctly, so SELL slippage is adverse.
        quote_source=ReplayQuoteSource(source, Decimal(quote_slippage)),
        candle_source=source,
        store=store,
    )
    state = store.load_or_start(SOL, "momentum", config.backtest.initial_capital_usd,
                               now=candles[warmup].timestamp)

    coverage = Coverage()
    while not source.exhausted:
        result = trader.run_tick_and_save(state, now=source.now)
        coverage.record(result)
        source.advance()
    return state, coverage, len(candles) - warmup


class ReplayQuoteSource(MockQuoteSource):
    """Prices every quote off the bar currently being replayed."""

    def __init__(self, source: ReplayCandleSource, slippage_pct: Decimal) -> None:
        super().__init__(slippage_pct=slippage_pct)
        self._source = source

    def get_quote(self, *args, **kwargs):
        window = self._source.fetch_candles("", limit=1)
        if window:
            self.expected_price = window[-1].close
        return super().get_quote(*args, **kwargs)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pool", default="8sLbNZoA1cfnvMJLPfp98ZLAnFSYCFApfJKMbiXNLwxj")
    ap.add_argument("--interval", default="15m")
    ap.add_argument("--warmup", type=int, default=60, help="bars withheld before the first tick")
    ap.add_argument("--slippage", default="0.2", help="quote slippage percent")
    args = ap.parse_args()

    state, cov, ticks = simulate(args.pool, args.interval, args.warmup, args.slippage)

    print(f"\n=== replay: {args.interval}, {ticks} ticks over real cached bars ===\n")
    print("LIFECYCLE COVERAGE (the primary output)")
    for action, n in cov.actions.most_common():
        print(f"  {action:<22} {n:>5}")
    if cov.exit_reasons:
        print("\n  exits by reason")
        for reason, n in cov.exit_reasons.most_common():
            print(f"    {reason:<20} {n:>5}")
    if cov.block_reasons:
        print("\n  entries blocked by risk")
        for reason, n in cov.block_reasons.most_common():
            print(f"    {reason:<58} {n:>4}")
    if cov.errors:
        print("\n  errors")
        for err, n in cov.errors.most_common():
            print(f"    {err:<42} {n:>4}")

    untouched = [
        branch
        for branch in ("entered", "exited", "entry_blocked", "holding_position")
        if cov.actions.get(branch, 0) == 0
    ]
    print(f"\n  BRANCHES REAL DATA NEVER REACHED: {untouched or 'none'}")

    print("\nP&L (reported last on purpose — this is not evidence of edge)")
    print(f"  trades={len(state.trades)} net=${state.net_pnl_usd:.4f} "
          f"fees=${state.total_fees_usd:.4f} maxDD={state.max_drawdown_pct:.2f}%")
    print("\n  Trade count here measures machinery coverage, not signal quality.")
    print("  Edge questions go through research/walk_forward.py, never this file.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
