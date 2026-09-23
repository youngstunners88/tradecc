"""The detection-floor arithmetic that now gates strategy search.

If these numbers are wrong, the project spends months testing hypotheses it
cannot resolve — so the relations are pinned rather than trusted.
"""

from __future__ import annotations

import importlib.util
import sys
from decimal import Decimal
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

spec = importlib.util.spec_from_file_location("trade_power", ROOT / "research" / "trade_power.py")
trade_power = importlib.util.module_from_spec(spec)
sys.modules["trade_power"] = trade_power
spec.loader.exec_module(trade_power)

Power = trade_power.Power
FIXED = trade_power.DEFAULT_FIXED_COST_USD
STDEV = trade_power.DEFAULT_RETURN_STDEV_FRAC


def power(size: str) -> "trade_power.Power":
    return Power(Decimal(size), FIXED, STDEV)


def test_break_even_edge_rises_as_size_falls():
    """Fixed costs do not scale, so a smaller position must clear a bigger
    percentage hurdle. This is the whole reason $5 is harder than $100."""
    assert power("5").break_even_edge > power("10").break_even_edge
    assert power("10").break_even_edge > power("100").break_even_edge
    assert power("5").break_even_edge == pytest.approx(Decimal("0.00254"), abs=Decimal("0.00001"))


def test_an_edge_below_break_even_is_never_detectable():
    """Not 'needs more trades' — impossible. A 0.2% gross edge on $5 is
    $0.010 against $0.0127 of cost, so the trade loses money by construction
    and no sample size changes that."""
    assert power("5").trades_needed(Decimal("0.002")) is None
    assert power("10").trades_needed(Decimal("0.002")) is not None


def test_a_strong_edge_is_cheap_to_confirm_even_at_small_size():
    """The finding that supports trading small: a 1% gross edge needs about a
    dozen round trips at $5-10, not a 30-day window."""
    assert power("5").trades_needed(Decimal("0.01")) < Decimal(20)
    assert power("10").trades_needed(Decimal("0.01")) < Decimal(15)


def test_a_weak_edge_is_impractical_at_any_size_we_trade():
    assert power("10").trades_needed(Decimal("0.002")) > Decimal(1000)
    assert power("100").trades_needed(Decimal("0.002")) > Decimal(150)


def test_trades_needed_falls_as_the_edge_grows():
    p = power("10")
    counts = [p.trades_needed(Decimal(str(e))) for e in (0.005, 0.01, 0.02)]
    assert counts == sorted(counts, reverse=True)


def test_minimum_detectable_edge_falls_as_the_budget_grows():
    p = power("10")
    assert p.minimum_detectable_edge(20) > p.minimum_detectable_edge(200)


def test_the_two_directions_agree():
    """trades_needed and minimum_detectable_edge solve the same relation. If
    they disagree, one of them is wrong and the gate built on it is wrong."""
    p = power("10")
    edge = Decimal("0.01")
    n = int(p.trades_needed(edge))
    recovered = p.minimum_detectable_edge(n)
    assert recovered == pytest.approx(edge, rel=Decimal("0.05"))


def test_a_thirty_day_window_cannot_confirm_a_sub_quarter_percent_edge():
    """The gate's window WAS 30 days. At ~2.35 round trips/day that is ~70
    trades, which cannot resolve anything under about 0.33% even at $100.
    Kept as the reference point for the 2-day window below."""
    budget = 70
    for size in ("5", "10", "25", "100"):
        assert power(size).minimum_detectable_edge(budget) > Decimal("0.003")


def test_the_two_day_window_detects_strictly_less_than_the_thirty_day_one():
    """The gate's window is now 2 days (user decision, 2026-09-23). At ~2.35
    round trips/day that is ~5 trades. This does not argue with the decision;
    it records what the window can see, so a pass is read for what it is.

    The calendar check is not what makes the gate safe on its own -- the
    pooled-trade minimum, drawdown threshold and human approval still have to
    pass independently.
    """
    for size in ("5", "10", "25", "100"):
        two_day = power(size).minimum_detectable_edge(5)
        thirty_day = power(size).minimum_detectable_edge(70)
        assert two_day > thirty_day
