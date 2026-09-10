"""Walk-forward validation harness.

Protocol is fixed in
planning/decisions/2026-09-10-walk-forward-validation.md and this module
implements it literally. Phase A (baseline, no search) is what runs now;
Phase B (search) is defined in the record but is not built here until
Phase A is reported and approved.

Phase A relies on one fact: with parameters held fixed, a single causal
backtest over the whole series produces exactly the trades each expanding
fold would produce, so folds are formed by bucketing trades on their
entry timestamp. Phase B cannot use that shortcut — it changes parameters
per fold — which is why this file scores only the baseline and refuses to
pretend otherwise.

Kept in research/ because it is an analysis tool, not part of the bot.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from backtest.runner import BacktestResult, BacktestRunner  # noqa: E402
from core.config import load_config  # noqa: E402
from core.performance import (  # noqa: E402
    ClosedTrade,
    expectancy,
    gross_pnl,
    net_pnl,
    total_fees,
    win_rate_pct,
)
from core.types import Candle  # noqa: E402
from execution.candle_cache import CandleCache  # noqa: E402
from strategy.strategy_momentum import MomentumParams, MomentumStrategy  # noqa: E402

# Fixed in the decision record, before the harness existed.
FOLD_COUNT = 3
INTERVALS = ["1h", "4h", "15m"]  # 1d excluded: too few trades to learn from.


@dataclass(frozen=True)
class FoldResult:
    index: int
    first_candle: str
    last_candle: str
    trades: list[ClosedTrade]

    @property
    def trade_count(self) -> int:
        return len(self.trades)

    @property
    def net(self) -> Decimal:
        return net_pnl(self.trades)

    @property
    def gross(self) -> Decimal:
        return gross_pnl(self.trades)

    @property
    def fees(self) -> Decimal:
        return total_fees(self.trades)

    @property
    def expectancy(self) -> Decimal:
        return expectancy(self.trades)

    @property
    def win_rate(self) -> Decimal:
        return win_rate_pct(self.trades)


@dataclass(frozen=True)
class Verdict:
    """The locked decision rule, evaluated — never re-tuned to pass."""

    majority_positive: bool  # net > 0 in >= 2 of 3 folds
    pooled_positive: bool  # pooled net > 0
    not_concentrated: bool  # no fold > 60% of pooled net
    enough_trades: bool  # pooled trade count >= 12

    @property
    def replicated(self) -> bool:
        return all(
            (
                self.majority_positive,
                self.pooled_positive,
                self.not_concentrated,
                self.enough_trades,
            )
        )


def fold_bounds(n: int, folds: int) -> list[tuple[int, int]]:
    """Consecutive equal-length windows by candle index, tiling [0, n).

    The final window absorbs any remainder so no candle is dropped.
    """
    size = n // folds
    bounds = [(i * size, (i + 1) * size) for i in range(folds)]
    bounds[-1] = (bounds[-1][0], n)
    return bounds


def baseline_folds(
    result: BacktestResult, candles: list[Candle], folds: int
) -> list[FoldResult]:
    """Bucket a whole-series backtest's trades into folds by entry time.

    Valid only because Phase A holds parameters fixed across folds; see
    the module docstring.
    """
    entry_index = {c.timestamp: i for i, c in enumerate(candles)}
    bounds = fold_bounds(len(candles), folds)
    buckets: list[list[ClosedTrade]] = [[] for _ in bounds]
    for trade in result.trades:
        i = entry_index.get(trade.entry_at)
        if i is None:
            continue
        for fold, (lo, hi) in enumerate(bounds):
            if lo <= i < hi:
                buckets[fold].append(trade)
                break
    return [
        FoldResult(
            index=fold,
            first_candle=candles[lo].timestamp.date().isoformat(),
            last_candle=candles[hi - 1].timestamp.date().isoformat(),
            trades=buckets[fold],
        )
        for fold, (lo, hi) in enumerate(bounds)
    ]


def judge(folds: list[FoldResult]) -> Verdict:
    pooled = sum((f.net for f in folds), Decimal(0))
    pooled_trades = sum(f.trade_count for f in folds)
    positive_folds = sum(1 for f in folds if f.net > 0)
    # Concentration is only meaningful when the pooled result is positive;
    # a fold cannot "carry" a result that does not exist.
    if pooled > 0:
        biggest = max((f.net for f in folds), default=Decimal(0))
        not_concentrated = biggest <= pooled * Decimal("0.60")
    else:
        not_concentrated = False
    return Verdict(
        majority_positive=positive_folds >= 2,
        pooled_positive=pooled > 0,
        not_concentrated=not_concentrated,
        enough_trades=pooled_trades >= 12,
    )


def run_phase_a(config_path: str) -> int:
    config = load_config(config_path, env={})
    cache = CandleCache(config.data.cache_dir)
    token = config.strategy.token_mints[0]

    print("PHASE A — baseline (default parameters, no search)")
    print("Protocol: planning/decisions/2026-09-10-walk-forward-validation.md")
    print(f"Params:   {MomentumParams()}\n")

    for interval in INTERVALS:
        candles = cache.load(config.paper.pool_address, interval)
        result = BacktestRunner(config, MomentumStrategy(MomentumParams())).run(
            token, candles
        )
        folds = baseline_folds(result, candles, FOLD_COUNT)
        verdict = judge(folds)

        print("=" * 72)
        print(
            f"{interval}  |  {len(candles)} candles  "
            f"{candles[0].timestamp.date()} -> {candles[-1].timestamp.date()}  |  "
            f"whole-series net {result.net_pnl_usd:+.4f} ({result.trade_count} trades)"
        )
        print("=" * 72)
        print(
            f"{'fold':<6}{'window':<26}{'trades':>7}{'gross':>9}"
            f"{'fees':>8}{'net':>9}{'win%':>7}"
        )
        for f in folds:
            print(
                f"{f.index:<6}{f.first_candle + ' -> ' + f.last_candle:<26}"
                f"{f.trade_count:>7}{f.gross:>9.4f}{f.fees:>8.4f}"
                f"{f.net:>9.4f}{f.win_rate:>7.1f}"
            )
        pooled = sum((f.net for f in folds), Decimal(0))
        pooled_trades = sum(f.trade_count for f in folds)
        print(f"{'pool':<6}{'(all folds)':<26}{pooled_trades:>7}{'':>9}{'':>8}"
              f"{pooled:>9.4f}")
        print()
        print(f"  decision rule (locked):")
        print(f"    net>0 in >=2/3 folds ......... {_mark(verdict.majority_positive)}")
        print(f"    pooled net > 0 .............. {_mark(verdict.pooled_positive)}")
        print(f"    no fold > 60% of pooled ..... {_mark(verdict.not_concentrated)}")
        print(f"    pooled trades >= 12 ......... {_mark(verdict.enough_trades)}"
              f"  ({pooled_trades})")
        print(f"    => REPLICATED: {verdict.replicated}")
        print()

    return 0


def _mark(ok: bool) -> str:
    return "PASS" if ok else "FAIL"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config.backtest.yaml")
    parser.add_argument("--phase", choices=["a"], default="a")
    args = parser.parse_args()
    # Phase B is defined in the decision record but deliberately not
    # implemented until Phase A is reported and approved.
    return run_phase_a(args.config)


if __name__ == "__main__":
    raise SystemExit(main())
