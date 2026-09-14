"""How many trades until we know? And what edge is too small to ever detect?

The project's plan is to trade small, watch real results, and scale what works.
That plan has a measurable floor, and this computes it.

Two numbers decide everything, and neither depends on optimism:

1. **Break-even edge.** Fixed cost per round trip is ~$0.0127 regardless of
   size. At $5 a position, a gross edge below 0.254% is not merely hard to
   detect — it is *negative after costs*. No sample size fixes that.

2. **Minimum detectable edge.** Per-trade returns have a standard deviation of
   about 0.95% of position size (measured, not assumed). Distinguishing a true
   edge from luck needs roughly `(z_a + z_b)^2 * (sigma/mu)^2` round trips.
   Below some edge, that number exceeds any window we will actually run.

The useful consequence is a **filter on strategy search**: there is no point
testing a hypothesis whose plausible edge sits under the detection floor for
the size we trade, because the test cannot return a trustworthy answer either
way. That filter has never been applied here — momentum was tested six ways at
an edge far below it.

    PYTHONPATH=src .venv/bin/python research/trade_power.py
    PYTHONPATH=src .venv/bin/python research/trade_power.py --size 5 --trades-per-day 2.35
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from decimal import Decimal

# 95% confidence, 80% power. (1.96 + 0.8416)^2
Z_SQUARED = Decimal("7.8489")

# Measured recurring fixed cost per round trip — research/calibrate_costs.py.
# Excludes the one-off refundable ATA rent, which is a deposit, not a fee.
DEFAULT_FIXED_COST_USD = Decimal("0.0127")

# Per-trade net return standard deviation as a fraction of position size,
# measured over the recorded SOL/USDC 15m backtest (23 round trips): 0.951%.
# It is a property of the market and the holding period, not of the strategy's
# edge, so it transfers to any strategy trading the same pair on the same bars.
DEFAULT_RETURN_STDEV_FRAC = Decimal("0.00951")


@dataclass(frozen=True)
class Power:
    size_usd: Decimal
    fixed_cost_usd: Decimal
    return_stdev_frac: Decimal

    @property
    def break_even_edge(self) -> Decimal:
        """Gross edge per round trip below which the trade loses money by
        construction. Fixed costs do not scale, so this rises as size falls."""
        return self.fixed_cost_usd / self.size_usd

    def trades_needed(self, gross_edge: Decimal) -> Decimal | None:
        """Round trips to distinguish this edge from zero. None if never."""
        net = self.size_usd * gross_edge - self.fixed_cost_usd
        if net <= 0:
            return None
        sigma = self.size_usd * self.return_stdev_frac
        return Z_SQUARED * (sigma / net) ** 2

    def minimum_detectable_edge(self, budget_trades: int) -> Decimal | None:
        """The smallest gross edge a run of `budget_trades` could confirm.

        Solves the same relation for the edge instead of the count. Returns
        None when no edge is detectable in that many trades, which happens
        when the budget is smaller than the count needed even for a large edge.
        """
        sigma = self.size_usd * self.return_stdev_frac
        if budget_trades <= 0:
            return None
        # net = sigma * sqrt(Z2 / n)
        net = sigma * (Z_SQUARED / Decimal(budget_trades)).sqrt()
        return (net + self.fixed_cost_usd) / self.size_usd


def report(sizes, edges, trades_per_day: Decimal, fixed: Decimal, stdev: Decimal) -> None:
    print(f"\nassumptions: fixed cost ${fixed}/round trip, "
          f"per-trade stdev {stdev * 100:.3f}% of size, "
          f"{trades_per_day} round trips/day\n")

    print("BREAK-EVEN GROSS EDGE — below this the trade loses money by construction")
    for s in sizes:
        p = Power(s, fixed, stdev)
        print(f"  ${s:>6}  {p.break_even_edge * 100:>6.3f}% per round trip")

    print("\nROUND TRIPS NEEDED to tell a real edge from luck")
    print(f"  {'edge':>8} | " + " | ".join(f"${s:>7}" for s in sizes))
    print("  " + "-" * (10 + 11 * len(sizes)))
    for e in edges:
        cells = []
        for s in sizes:
            n = Power(s, fixed, stdev).trades_needed(e)
            cells.append("  never" if n is None else f"{n:>7.0f}")
        print(f"  {e * 100:>7.2f}% | " + " | ".join(f"{c:>8}" for c in cells))

    print("\nCALENDAR TIME to a verdict")
    print(f"  {'edge':>8} | " + " | ".join(f"${s:>7}" for s in sizes))
    print("  " + "-" * (10 + 11 * len(sizes)))
    for e in edges:
        cells = []
        for s in sizes:
            n = Power(s, fixed, stdev).trades_needed(e)
            if n is None:
                cells.append("  never")
            else:
                days = n / trades_per_day
                cells.append(f"{days / 30:>6.1f}mo" if days > 60 else f"{days:>6.1f}d")
        print(f"  {e * 100:>7.2f}% | " + " | ".join(f"{c:>8}" for c in cells))

    print("\nWHAT A 30-DAY RUN CAN CONFIRM (the gate's own window)")
    for s in sizes:
        p = Power(s, fixed, stdev)
        budget = int(trades_per_day * 30)
        mde = p.minimum_detectable_edge(budget)
        print(f"  ${s:>6}  {budget:>4} round trips  ->  smallest confirmable edge "
              f"{mde * 100:>6.3f}% per round trip")

    print("\nRead this as a filter on what to look for, not a forecast.")
    print("A hypothesis whose plausible edge sits under the floor for our size")
    print("cannot be tested at our size — the answer would not be trustworthy")
    print("either way, so the honest move is to not spend the window on it.\n")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--size", type=Decimal, action="append",
                    help="position size in USD (repeatable; default 5/10/25/100)")
    ap.add_argument("--trades-per-day", type=Decimal, default=Decimal("2.35"),
                    help="observed round trips per day (15m SOL/USDC: 2.35)")
    ap.add_argument("--fixed-cost", type=Decimal, default=DEFAULT_FIXED_COST_USD)
    ap.add_argument("--stdev", type=Decimal, default=DEFAULT_RETURN_STDEV_FRAC)
    args = ap.parse_args()

    sizes = args.size or [Decimal(5), Decimal(10), Decimal(25), Decimal(100)]
    edges = [Decimal("0.002"), Decimal("0.005"), Decimal("0.01"), Decimal("0.02")]
    report(sizes, edges, args.trades_per_day, args.fixed_cost, args.stdev)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
