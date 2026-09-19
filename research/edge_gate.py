"""The viability gate, as a callable function instead of a habit.

`.claude/skills/edge-viability-check` describes a four-step gate that every
strategy hypothesis is supposed to clear *before* a backtest is written. It
was never callable — it lived in a skill document, which means it ran only
when somebody remembered to read it. Four hypotheses on this project were
tested correctly and were unanswerable before the first line of harness code,
because nobody ran the arithmetic first.

This module makes that arithmetic a function, so it can run in a second from
a CLI, a test, or the MCP server in `research/edge_gate_mcp.py`.

**It reimplements nothing.** The arithmetic lives in `research/trade_power.py`
and this imports `Power` from it. The registry already rejected a pasted
`validation_gate.py` for exactly this reason: one gate, one implementation. A
second copy of the maths would drift from the first and nobody would know
which was right.

What it does *not* do is step 4 — whether the return distribution actually
contains the claimed edge. That needs real bars and lives in
`research/edge_budget.py`. This returns a pointer to that script rather than
guessing, because a gate that fabricates its hardest step is worse than one
that admits the gap.

    PYTHONPATH=src .venv/bin/python research/edge_gate.py --edge 0.5 --size 10
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from dataclasses import dataclass, asdict
from decimal import Decimal
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent


def _load_trade_power():
    """Load trade_power.py by path. It is a script, not an installed module."""
    spec = importlib.util.spec_from_file_location(
        "trade_power", _HERE / "trade_power.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("trade_power", module)
    spec.loader.exec_module(module)
    return module


_tp = _load_trade_power()
Power = _tp.Power
DEFAULT_FIXED_COST_USD = _tp.DEFAULT_FIXED_COST_USD
DEFAULT_RETURN_STDEV_FRAC = _tp.DEFAULT_RETURN_STDEV_FRAC
Z_SQUARED = _tp.Z_SQUARED

# Raised from 12 on 2026-09-16: 12 sat below this project's own detection
# floor (7.8489 * 1.33^2 = 13.88 round trips) even for a perfect strategy.
# See .claude/skills/backtesting/SKILL.md for the full reasoning.
REPLICATION_MIN_POOLED_TRADES = 19

# The gate window from planning/specs/mvp_spec.md.
DEFAULT_WINDOW_DAYS = 30

# Measured on the SOL/USDC 15m backtest. Only used to convert a window in days
# into a trade count when the caller does not supply one.
DEFAULT_TRADES_PER_DAY = Decimal("2.35")


@dataclass(frozen=True)
class StepResult:
    step: int
    name: str
    passed: bool | None  # None = cannot be decided here
    detail: str


@dataclass(frozen=True)
class GateVerdict:
    verdict: str  # PASS | FAIL | INCOMPLETE
    claimed_gross_edge_pct: float | None
    size_usd: float
    break_even_pct: float
    trades_needed: float | None
    trades_available: float
    window_days: int
    steps: list[dict[str, Any]]
    summary: str

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2)


def check(
    claimed_gross_edge_pct: Decimal | float | None,
    size_usd: Decimal | float = Decimal("10"),
    window_days: int = DEFAULT_WINDOW_DAYS,
    trades_per_day: Decimal | float = DEFAULT_TRADES_PER_DAY,
    fixed_cost_usd: Decimal | float = DEFAULT_FIXED_COST_USD,
    return_stdev_frac: Decimal | float = DEFAULT_RETURN_STDEV_FRAC,
) -> GateVerdict:
    """Run steps 1-3 of the viability gate. Step 4 needs bars; see the docstring.

    `claimed_gross_edge_pct` is gross percent per round trip, e.g. 0.5 for
    0.5%. Pass None when the hypothesis has not stated one — that is itself a
    failure at step 1, and the most common one.
    """
    size = Decimal(str(size_usd))
    fixed = Decimal(str(fixed_cost_usd))
    stdev = Decimal(str(return_stdev_frac))
    per_day = Decimal(str(trades_per_day))
    power = Power(size_usd=size, fixed_cost_usd=fixed, return_stdev_frac=stdev)

    break_even = power.break_even_edge
    trades_available = per_day * Decimal(window_days)
    steps: list[StepResult] = []

    # --- Step 1: is there a number at all? -------------------------------
    if claimed_gross_edge_pct is None:
        steps.append(StepResult(
            1, "claimed edge stated", False,
            "No gross % per round trip was given. 'It should be profitable' is "
            "not an edge estimate. The gate cannot proceed, and this is the "
            "most common way a hypothesis fails — before any data is touched.",
        ))
        return _assemble(
            None, size, break_even, None, trades_available, window_days, steps,
        )

    edge = Decimal(str(claimed_gross_edge_pct)) / Decimal(100)
    steps.append(StepResult(
        1, "claimed edge stated", True,
        f"{claimed_gross_edge_pct}% gross per round trip.",
    ))

    # --- Step 2: does it clear break-even? -------------------------------
    clears_break_even = edge > break_even
    steps.append(StepResult(
        2, "clears break-even", clears_break_even,
        f"Break-even at ${size} is {break_even * 100:.3f}% "
        f"(fixed cost ${fixed} does not scale down). "
        + (
            f"Claimed {claimed_gross_edge_pct}% clears it."
            if clears_break_even
            else f"Claimed {claimed_gross_edge_pct}% is BELOW it — negative by "
                 "construction. No sample size fixes a negative expectancy."
        ),
    ))
    if not clears_break_even:
        return _assemble(
            edge, size, break_even, None, trades_available, window_days, steps,
        )

    # --- Step 3: is it detectable in the window we will actually run? ----
    needed = power.trades_needed(edge)
    if needed is None:
        steps.append(StepResult(
            3, "detectable in window", False,
            "Net expectancy is non-positive, so no number of trades "
            "distinguishes it from zero.",
        ))
        return _assemble(
            edge, size, break_even, None, trades_available, window_days, steps,
        )

    detectable = needed <= trades_available
    meets_replication = trades_available >= REPLICATION_MIN_POOLED_TRADES
    detail = (
        f"Needs {needed:.1f} round trips to separate from zero at 95/80. "
        f"A {window_days}-day window at {per_day}/day yields "
        f"{trades_available:.1f}."
    )
    if not detectable:
        detail += (
            f" Short by {needed - trades_available:.1f}. The test cannot come "
            "back trustworthy either way — this is the step that would have "
            "saved the four hypotheses tested before it existed."
        )
    if not meets_replication:
        detail += (
            f" Separately, {trades_available:.1f} is below the replication "
            f"rule's pooled minimum of {REPLICATION_MIN_POOLED_TRADES}."
        )
    steps.append(StepResult(
        3, "detectable in window", detectable and meets_replication, detail,
    ))

    # --- Step 4: does the distribution contain it? -----------------------
    steps.append(StepResult(
        4, "distribution contains it", None,
        "Not decidable here — needs real bars. Run "
        "`PYTHONPATH=src .venv/bin/python research/edge_budget.py "
        f"--size {size} --cross-asset`. Above ~60% required direction accuracy "
        "is a red flag; above 70% is a refutation. For a STRUCTURAL hypothesis "
        "substitute frequency x payoff, and note steps 1-3 still apply in full.",
    ))

    return _assemble(
        edge, size, break_even, needed, trades_available, window_days, steps,
    )


def _assemble(
    edge: Decimal | None,
    size: Decimal,
    break_even: Decimal,
    needed: Decimal | None,
    trades_available: Decimal,
    window_days: int,
    steps: list[StepResult],
) -> GateVerdict:
    hard_failed = any(s.passed is False for s in steps)
    undecided = any(s.passed is None for s in steps)
    if hard_failed:
        verdict = "FAIL"
        summary = (
            "Does not clear the gate. "
            + next(s.detail for s in steps if s.passed is False)
        )
    elif undecided:
        verdict = "INCOMPLETE"
        summary = (
            "Steps 1-3 pass. Step 4 needs edge_budget.py against real bars "
            "before this is a permission to test. A pass is never evidence an "
            "edge exists — only that the measurement could see one if it did."
        )
    else:
        verdict = "PASS"
        summary = "All decidable steps pass."
    return GateVerdict(
        verdict=verdict,
        claimed_gross_edge_pct=float(edge * 100) if edge is not None else None,
        size_usd=float(size),
        break_even_pct=float(break_even * 100),
        trades_needed=float(needed) if needed is not None else None,
        trades_available=float(trades_available),
        window_days=window_days,
        steps=[asdict(s) for s in steps],
        summary=summary,
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--edge", type=Decimal, default=None,
                    help="Claimed gross %% per round trip, e.g. 0.5. Omit to "
                         "see what an unstated edge does (it fails step 1).")
    ap.add_argument("--size", type=Decimal, default=Decimal("10"))
    ap.add_argument("--window-days", type=int, default=DEFAULT_WINDOW_DAYS)
    ap.add_argument("--trades-per-day", type=Decimal, default=DEFAULT_TRADES_PER_DAY)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    result = check(
        claimed_gross_edge_pct=args.edge,
        size_usd=args.size,
        window_days=args.window_days,
        trades_per_day=args.trades_per_day,
    )
    if args.json:
        print(result.to_json())
    else:
        print(f"VERDICT: {result.verdict}\n")
        for s in result.steps:
            mark = {True: "PASS", False: "FAIL", None: "N/A "}[s["passed"]]
            print(f"  [{mark}] step {s['step']}: {s['name']}")
            print(f"         {s['detail']}\n")
        print(result.summary)
    return 0 if result.verdict != "FAIL" else 1


if __name__ == "__main__":
    raise SystemExit(main())
