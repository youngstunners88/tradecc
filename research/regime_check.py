"""Step-4 mechanism check for the regime-detection hypothesis.

`.claude/skills/regime-detection/SKILL.md` prescribes one check before any
regime parameter is tried: label the existing history by regime and compare
expectancy in trend-labelled windows against chop-labelled windows, **at the
default parameters**. If the gap is not there at defaults, regime conditioning
is not the explanation for the momentum failure and tuning until it appears is
fitting noise.

This file runs exactly that check and nothing else. It fits no threshold,
selects no configuration, and reports every interval. It is a pre-registration
probe: it answers "is the hypothesis testable on this data" before a decision
record fixes a protocol, in the same spirit as the universe probe that opened
`planning/decisions/2026-09-12-cross-sectional-momentum-protocol.md`.

Classifier: Kaufman efficiency ratio, the skill's own first choice.

    ER[i] = |close[i] - close[i-w]| / sum(|close[k] - close[k-1]|), k in (i-w, i]

Point-in-time: ER at bar i reads closes[i-w..i] only. Trades are stamped at bar
CLOSE (see `research/walk_forward.py`), so a trade's entry bar is the bar whose
close time equals `entry_at` — the same indexing the walk-forward harness uses.
Analysis tool, not part of the bot.
"""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from backtest.runner import BacktestRunner  # noqa: E402
from core.config import load_config  # noqa: E402
from core.performance import ClosedTrade, expectancy, net_pnl  # noqa: E402
from core.types import Candle  # noqa: E402
from execution.candle_cache import CandleCache  # noqa: E402
from strategy.strategy_momentum import MomentumParams, MomentumStrategy  # noqa: E402

INTERVALS = ["1h", "4h", "15m"]
ER_WINDOW = 20
# Conventional split point, named before running. Not fitted, not searched.
TREND_THRESHOLD = Decimal("0.4")


def efficiency_ratio(
    closes: list[Decimal], window: int = ER_WINDOW
) -> list[Decimal | None]:
    """Kaufman efficiency ratio, aligned to input length, None during warmup."""
    out: list[Decimal | None] = [None] * len(closes)
    for i in range(window, len(closes)):
        churn = sum(
            (abs(closes[k] - closes[k - 1]) for k in range(i - window + 1, i + 1)),
            Decimal(0),
        )
        if churn == 0:
            continue
        out[i] = abs(closes[i] - closes[i - window]) / churn
    return out


def quantile(values: list[Decimal], q: Decimal) -> Decimal:
    """Nearest-rank quantile. Exact on Decimals, no float round-trip."""
    ordered = sorted(values)
    rank = int((q * Decimal(len(ordered))).to_integral_value(rounding="ROUND_CEILING"))
    return ordered[max(0, min(rank - 1, len(ordered) - 1))]


def label_flips(labels: list[bool | None]) -> int:
    """How many times the regime label changes across the series."""
    seen = [x for x in labels if x is not None]
    return sum(1 for a, b in zip(seen, seen[1:]) if a != b)


def close_index(candles: list[Candle]) -> dict:
    """Map bar CLOSE time -> index, matching how trades are stamped."""
    bar = candles[1].timestamp - candles[0].timestamp if len(candles) >= 2 else None
    return {(c.timestamp + bar if bar else c.timestamp): i for i, c in enumerate(candles)}


def summarise(name: str, trades: list[ClosedTrade]) -> str:
    if not trades:
        return f"  {name:<26} n=0        (empty arm)"
    return (
        f"  {name:<26} n={len(trades):<3} "
        f"net {net_pnl(trades):+8.4f}   expectancy {expectancy(trades):+7.4f}"
    )


def run(config_path: str = "config.backtest.yaml") -> int:
    config = load_config(config_path, env={})
    cache = CandleCache(config.data.cache_dir)
    token = config.strategy.token_mints[0]

    print("REGIME PRE-REGISTRATION CHECK — step 4 of the regime-detection skill")
    print(f"Classifier: Kaufman efficiency ratio, window {ER_WINDOW}")
    print(f"Trend threshold: ER >= {TREND_THRESHOLD} (named before running)")
    print(f"Params: {MomentumParams()} (defaults, unchanged)\n")

    for interval in INTERVALS:
        candles = cache.load(config.paper.pool_address, interval)
        closes = [c.close for c in candles]
        er = efficiency_ratio(closes)
        measured = [x for x in er if x is not None]
        labels = [None if x is None else x >= TREND_THRESHOLD for x in er]

        result = BacktestRunner(config, MomentumStrategy(MomentumParams())).run(
            token, candles
        )
        index = close_index(candles)

        trend: list[ClosedTrade] = []
        chop: list[ClosedTrade] = []
        entry_ers: list[Decimal] = []
        for trade in result.trades:
            i = index.get(trade.entry_at)
            if i is None or er[i] is None:
                continue
            entry_ers.append(er[i])
            (trend if labels[i] else chop).append(trade)

        print("=" * 72)
        print(
            f"{interval}  |  {len(candles)} candles  "
            f"{candles[0].timestamp.date()} -> {candles[-1].timestamp.date()}  |  "
            f"{result.trade_count} trades at defaults"
        )
        print("=" * 72)
        print(
            f"  ER over all bars:  median {quantile(measured, Decimal('0.5')):.3f}   "
            f"p90 {quantile(measured, Decimal('0.9')):.3f}   "
            f"max {max(measured):.3f}"
        )
        share = Decimal(sum(1 for x in measured if x >= TREND_THRESHOLD)) / Decimal(
            len(measured)
        ) * 100
        print(
            f"  bars labelled TREND: {share:.1f}%   "
            f"label flips across series: {label_flips(labels)}"
        )
        if entry_ers:
            print(
                f"  ER at trade entries: median "
                f"{quantile(entry_ers, Decimal('0.5')):.3f}   "
                f"max {max(entry_ers):.3f}"
            )
        print(summarise("TREND-labelled entries", trend))
        print(summarise("CHOP-labelled entries", chop))
        print()

    print("No threshold was fitted and no configuration was selected. The check")
    print("is prescribed by the skill; its answer is reported whichever way it")
    print("falls.")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
