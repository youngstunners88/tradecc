"""The edge-budget arithmetic that now bounds where a strategy may be sought.

Two errors were caught in this file's own first drafts, and both would have
flattered the result: applying one detection floor to every horizon (which
ignores that a longer hold yields fewer trades), and averaging skipped windows
into the oracle's gross while still counting every window as a trade. Both are
pinned here so they cannot come back.
"""

from __future__ import annotations

import importlib.util
import sys
from decimal import Decimal
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("edge_budget", ROOT / "research" / "edge_budget.py")
edge_budget = importlib.util.module_from_spec(spec)
sys.modules["edge_budget"] = edge_budget
spec.loader.exec_module(edge_budget)

Bars = edge_budget.Bars
budget_for = edge_budget.budget_for
SIZE = Decimal("10")


def flat_then_up(n: int = 40) -> Bars:
    """Alternating down/up bars, so exactly half the windows close up."""
    closes = [100.0 + (1.0 if i % 2 else 0.0) for i in range(n)]
    return Bars("1h", closes, [c * 1.01 for c in closes], [c * 0.99 for c in closes])


def trending(n: int = 40, step: float = 0.01) -> Bars:
    closes = [100.0 * (1 + step) ** i for i in range(n)]
    return Bars("1h", closes, closes, closes)


def test_windows_do_not_overlap():
    """Overlapping windows would count the same price move many times and
    inflate every figure derived from them."""
    bars = trending(41)
    b = budget_for(bars, 4)
    assert b is not None
    assert b.windows == pytest.approx(10, abs=1)


def test_the_oracle_is_measured_on_trades_taken_not_windows_seen():
    """A directional oracle skips losers. Averaging those skipped zeros into
    its gross while still counting them as trades understates the trade's size
    and overstates the sample — flattering every horizon at once."""
    b = budget_for(flat_then_up(60), 1)
    assert b is not None
    assert 0.0 < b.up_fraction < 1.0
    # Gross is the mean of winners only, so it must exceed the mean signed move.
    assert b.oracle_direction_gross > 0
    assert b.trades_per_window < b.windows_per_month


def test_the_detection_floor_rises_as_trades_fall():
    """The whole point of making the floor horizon-specific: a longer hold
    carries a bigger move but proves less."""
    bars = trending(400)
    short = budget_for(bars, 1)
    long_ = budget_for(bars, 8)
    assert short is not None and long_ is not None
    assert long_.trades_per_window < short.trades_per_window
    assert long_.detection_floor(SIZE) > short.detection_floor(SIZE)


def test_a_horizon_with_under_one_trade_per_window_confirms_nothing():
    b = budget_for(trending(400), 1)
    assert b is not None
    starved = edge_budget.Budget(
        interval=b.interval, horizon=b.horizon, windows=b.windows,
        mean_abs_move=b.mean_abs_move, return_stdev=b.return_stdev,
        oracle_direction_gross=b.oracle_direction_gross,
        oracle_timing_gross=b.oracle_timing_gross, up_fraction=0.001,
    )
    assert starved.detection_floor(SIZE) == Decimal("1")


def test_required_accuracy_inverts_the_capture_relation():
    """p = (target / E|move| + 1) / 2. At target == E|move|, p is certainty."""
    b = budget_for(flat_then_up(60), 1)
    assert b is not None
    assert b.required_accuracy(Decimal(str(b.mean_abs_move))) == pytest.approx(1.0)
    assert b.required_accuracy(Decimal("0")) == pytest.approx(0.5)


def test_an_unreachable_target_reports_impossible_not_a_number_above_one():
    b = budget_for(flat_then_up(60), 1)
    assert b is not None
    assert b.required_accuracy(Decimal(str(b.mean_abs_move * 2))) is None


def test_raw_accuracy_stays_comparable_past_impossible():
    """The verdict caps at certainty; the cross-asset comparison must not, or
    every impossible horizon looks equally impossible."""
    b = budget_for(flat_then_up(60), 1)
    assert b is not None
    target = Decimal(str(b.mean_abs_move * 2))
    assert b.required_accuracy(target) is None
    assert b.raw_accuracy(target) > 1.0


def test_a_series_too_short_to_form_windows_yields_nothing():
    assert budget_for(trending(6), 4) is None
