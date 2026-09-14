"""Where could an edge of the required size even live?

`research/trade_power.py` answers "how big must an edge be for us to detect it
at our size" — about 0.5% gross per round trip. This answers the question that
follows immediately: **at which holding periods is an edge that large even
physically available**, given how much the price actually moves?

The method is deliberately strategy-agnostic. It measures the realised return
distribution of real cached bars and derives, per horizon:

1. **The oracle ceiling.** What a trader who knew the future would net. Two
   versions: one that knows only the direction of the close-to-close move (and
   skips losers), and one that also times entry and exit perfectly within the
   window. No strategy at that horizon can beat these. If the ceiling sits
   below the detection floor, the horizon is dead and no amount of cleverness
   revives it.

2. **The required direction accuracy.** On a roughly symmetric move
   distribution, a directional caller with accuracy `p` captures about
   `(2p - 1) * E|move|` gross. Inverting that gives the accuracy needed to
   clear break-even and to clear the detection floor. "You must be right 54%
   of the time" is a research programme; "you must be right 81% of the time"
   is a refutation.

3. **The capture fraction.** What share of the average absolute move a
   strategy must convert into realised P&L.

None of this says an edge exists. It rules out places one cannot. That is
worth more than it sounds: this project spent six protocol-bound tests on a
hypothesis whose edge was far below the floor, and this is the check that
would have caught it in an afternoon.

    PYTHONPATH=src .venv/bin/python research/edge_budget.py
    PYTHONPATH=src .venv/bin/python research/edge_budget.py --size 5
"""

from __future__ import annotations

import argparse
import json
import statistics as stats
import sys
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

CACHE = ROOT / "research" / ".candle-cache"
DEFAULT_POOL = "8sLbNZoA1cfnvMJLPfp98ZLAnFSYCFApfJKMbiXNLwxj"

# Measured recurring cost per round trip — research/calibrate_costs.py.
FIXED_COST_USD = Decimal("0.0127")

# 95% confidence, 80% power — the same constant trade_power.py uses.
Z_SQUARED = 7.8489

# The gate's own window. The detection floor is computed PER HORIZON from the
# number of round trips that horizon yields inside it, because a longer hold
# produces fewer trades and therefore needs a bigger edge to be distinguished
# from luck. Applying one floor to every horizon — the first version of this
# file did — flatters long horizons badly: 1d x8 yields under four round trips
# in a month, and four trades cannot confirm anything.
GATE_WINDOW_DAYS = 30

# core.performance.MIN_POOLED_TRADES — the same floor the live gate applies.
MIN_TRADES = 12

BARS_PER_DAY = {"15m": 96, "1h": 24, "4h": 6, "1d": 1}


@dataclass(frozen=True)
class Bars:
    interval: str
    closes: list[float]
    highs: list[float]
    lows: list[float]

    def __len__(self) -> int:
        return len(self.closes)


def load(pool: str, interval: str) -> Bars | None:
    path = CACHE / f"{pool}_{interval}.json"
    if not path.is_file():
        return None
    rows = json.loads(path.read_text())
    return Bars(
        interval=interval,
        closes=[float(r["c"]) for r in rows],
        highs=[float(r["h"]) for r in rows],
        lows=[float(r["l"]) for r in rows],
    )


@dataclass(frozen=True)
class Budget:
    interval: str
    horizon: int
    windows: int
    mean_abs_move: float
    return_stdev: float
    # Per TRADE TAKEN, not per window. A directional oracle skips the windows
    # that close down, so its trade count and its average trade are on
    # different bases than the raw window count — averaging the skipped zeros
    # into the gross (the first version of this file did) understates the
    # oracle by about half while still crediting it with every window as a
    # trade. Both halves are now measured on trades actually taken.
    oracle_direction_gross: float
    oracle_timing_gross: float
    up_fraction: float

    @property
    def windows_per_month(self) -> float:
        return GATE_WINDOW_DAYS * BARS_PER_DAY[self.interval] / self.horizon

    @property
    def trades_per_window(self) -> float:
        """Round trips a DIRECTIONAL trader takes inside the gate window.

        Only the windows it judges tradeable. An oracle takes the up-windows;
        a real strategy takes some comparable fraction. Counting every window
        as a trade would credit a selective strategy with a sample it never
        collects.
        """
        return self.windows_per_month * self.up_fraction

    def detection_floor(self, size: Decimal) -> Decimal:
        """The smallest gross edge THIS horizon could confirm in the window.

        Two forces pull against each other: a longer hold carries a bigger
        move (easier to clear costs) but yields fewer trades (harder to prove).
        This is the number where they meet.
        """
        n = self.trades_per_window
        if n < 1:
            return Decimal("1")  # under one trade per window: nothing is confirmable
        spread = Decimal(str(self.return_stdev * (Z_SQUARED / n) ** 0.5))
        return spread + self.break_even_gross(size)

    def net(self, gross: float, size: Decimal) -> Decimal:
        return size * Decimal(str(gross)) - FIXED_COST_USD

    def break_even_gross(self, size: Decimal) -> Decimal:
        return FIXED_COST_USD / size

    def raw_accuracy(self, target_gross: Decimal) -> float:
        """The accuracy figure uncapped, so impossible horizons stay comparable.

        `required_accuracy` returns None above certainty, which is right for a
        verdict but hides how far past impossible a horizon sits — and that
        distance is exactly what a cross-asset comparison needs to show.
        """
        if self.mean_abs_move <= 0:
            return float("inf")
        return (float(target_gross) / self.mean_abs_move + 1.0) / 2.0

    def required_accuracy(self, target_gross: Decimal) -> float | None:
        """Direction accuracy needed to capture `target_gross` per round trip.

        gross ≈ (2p - 1) * E|move|  =>  p = (target / E|move| + 1) / 2

        Returns None when the answer exceeds certainty — which is the
        interesting case: it means the horizon cannot carry that edge even
        with a perfect directional call.
        """
        if self.mean_abs_move <= 0:
            return None
        p = (float(target_gross) / self.mean_abs_move + 1.0) / 2.0
        return p if p <= 1.0 else None


def budget_for(bars: Bars, horizon: int) -> Budget | None:
    """Non-overlapping windows only — overlapping ones would count the same
    price move many times and inflate every figure below."""
    moves: list[float] = []
    signed: list[float] = []
    oracle_dir: list[float] = []   # gross on up-windows only
    oracle_time: list[float] = []  # best achievable within each window

    for start in range(0, len(bars) - horizon, horizon):
        end = start + horizon
        entry = bars.closes[start]
        if entry <= 0:
            continue
        move = (bars.closes[end] - entry) / entry
        moves.append(abs(move))
        signed.append(move)
        # Knows the direction: takes the trade ONLY when it closes up, so this
        # list holds trades taken rather than windows seen.
        if move > 0:
            oracle_dir.append(move)
        # Also times it: buys the window's low, sells a later high. Long-only,
        # so the high must come after the low for the trade to be takeable.
        window_lows = bars.lows[start : end + 1]
        window_highs = bars.highs[start : end + 1]
        low_i = window_lows.index(min(window_lows))
        later = window_highs[low_i:]
        best = (max(later) - window_lows[low_i]) / window_lows[low_i] if later else 0.0
        oracle_time.append(max(best, 0.0))

    if len(moves) < 5:
        return None
    if not oracle_dir:
        return None
    return Budget(
        interval=bars.interval,
        horizon=horizon,
        windows=len(moves),
        mean_abs_move=stats.fmean(moves),
        return_stdev=stats.pstdev(signed) if len(signed) > 1 else 0.0,
        oracle_direction_gross=stats.fmean(oracle_dir),
        oracle_timing_gross=stats.fmean(oracle_time),
        up_fraction=len(oracle_dir) / len(moves),
    )


def report(budgets: list[Budget], size: Decimal) -> None:
    print(f"\nposition size ${size}; fixed cost ${FIXED_COST_USD}/round trip; "
          f"{GATE_WINDOW_DAYS}-day window\n")
    print(f"break-even gross: {FIXED_COST_USD / size * 100:.3f}% per round trip")
    print("required accuracy assumes a caller that takes a position every window")
    print("and is right with probability p; the oracle column is a selective")
    print("trader that takes only winners, so it is the looser of the two bounds.\n")

    print(f"  {'horizon':>10} {'trades/30d':>11} {'E|move|':>9} {'oracle':>9} "
          f"{'floor':>8} {'accuracy needed':>17}")
    print("  " + "-" * 70)
    for b in budgets:
        floor = b.detection_floor(size)
        acc = b.required_accuracy(floor)
        if b.trades_per_window < MIN_TRADES:
            verdict = "too few trades"
        elif acc is None:
            verdict = "DEAD"
        else:
            verdict = f"{acc * 100:.1f}%"
        print(f"  {b.interval + ' x' + str(b.horizon):>10} {b.trades_per_window:>11.1f} "
              f"{b.mean_abs_move * 100:>8.3f}% {b.oracle_direction_gross * 100:>8.3f}% "
              f"{float(floor) * 100:>7.3f}% {verdict:>17}")

    print(f"\n  DEAD           = unreachable even at 100% direction accuracy")
    print(f"  too few trades = under MIN_POOLED_TRADES ({MIN_TRADES}) in the window")

    print("\nFOR CONTEXT — accuracy needed merely to cover costs")
    print(f"  {'horizon':>10} {'break even':>12}")
    print("  " + "-" * 24)
    for b in budgets:
        be = b.required_accuracy(b.break_even_gross(size))
        print(f"  {b.interval + ' x' + str(b.horizon):>10} "
              f"{'impossible' if be is None else f'{be * 100:.1f}%':>12}")

    survivors = [
        b for b in budgets
        if b.trades_per_window >= MIN_TRADES and b.required_accuracy(b.detection_floor(size))
    ]
    print("\nHORIZONS THAT SURVIVE BOTH CONSTRAINTS")
    if not survivors:
        print("  none at this size.")
    else:
        best = min(survivors, key=lambda b: b.required_accuracy(b.detection_floor(size)))
        for b in survivors:
            acc = b.required_accuracy(b.detection_floor(size))
            mark = "  <- least demanding" if b is best else ""
            print(f"  {b.interval} x{b.horizon}: {acc * 100:.1f}% accuracy over "
                  f"{b.trades_per_window:.0f} round trips{mark}")

    print("\nThis rules horizons OUT; it never rules one in. A surviving horizon")
    print("means an edge there is not impossible — not that one exists. Published")
    print("directional accuracy on liquid crypto rarely clears the mid-50s, so a")
    print("horizon demanding 75% is a refutation in all but name.\n")


def cross_asset(size: Decimal) -> None:
    """Does trading something more volatile lower the bar?

    The intuition is that a bigger move is easier to profit from. It is wrong,
    and this measures why: volatility raises the edge available (E|move|) and
    the noise that must be overcome (stdev) together, so their ratio — which is
    what sets the required accuracy — barely moves. Only the fixed-cost term
    is relieved, and it is already small next to the noise at these levels.
    """
    rows = []
    for path in sorted(CACHE.glob("*_1d.json")):
        bars = load(path.name.split("_")[0], "1d")
        if bars is None or len(bars) < 40:
            continue
        b = budget_for(bars, 1)
        if b is None:
            continue
        rows.append((path.name.split("_")[0][:8], b))
    if len(rows) < 2:
        print("\nnot enough cached pools for a cross-asset comparison\n")
        return

    rows.sort(key=lambda r: r[1].mean_abs_move)
    print("\nDOES VOLATILITY HELP? — one day held, across every cached pool")
    print(f"  {'pool':<10}{'E|move|':>10}{'stdev':>9}{'noise ratio':>13}"
          f"{'floor':>9}{'accuracy':>10}")
    print("  " + "-" * 62)
    for name, b in rows:
        raw = b.raw_accuracy(b.detection_floor(size))
        ratio = b.return_stdev / b.mean_abs_move if b.mean_abs_move else 0
        flag = "" if raw <= 1.0 else " !"
        print(f"  {name:<10}{b.mean_abs_move * 100:>9.2f}%{b.return_stdev * 100:>8.2f}%"
              f"{ratio:>13.2f}{float(b.detection_floor(size)) * 100:>8.2f}%"
              f"{raw * 100:>9.1f}%{flag}")

    lo, hi = rows[0][1], rows[-1][1]
    span = hi.mean_abs_move / lo.mean_abs_move if lo.mean_abs_move else 0
    print(f"\n  {span:.1f}x range in volatility. The accuracy requirement moves by a")
    print("  few points and not monotonically: the noise ratio (stdev / E|move|) is")
    print("  what governs it, and volatility does not improve that ratio.")
    print("  Trading something wilder is not a route to profitability at this size.\n")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pool", default=DEFAULT_POOL)
    ap.add_argument("--size", type=Decimal, default=Decimal("10"))
    ap.add_argument("--cross-asset", action="store_true",
                    help="compare the accuracy requirement across cached pools")
    args = ap.parse_args()

    budgets: list[Budget] = []
    for interval in ("15m", "1h", "4h", "1d"):
        bars = load(args.pool, interval)
        if bars is None:
            continue
        for horizon in (1, 2, 4, 8):
            b = budget_for(bars, horizon)
            if b is not None:
                budgets.append(b)

    if not budgets:
        raise SystemExit(f"no cached candles for {args.pool}")
    report(budgets, args.size)
    if args.cross_asset:
        cross_asset(args.size)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
