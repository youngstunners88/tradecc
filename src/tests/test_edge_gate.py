"""The viability gate as a function — the cases it must never get wrong.

This gate exists because four hypotheses on this project were tested
correctly and were unanswerable before the harness was written. Its whole
value is refusing things early, so the tests that matter most are the
refusals: an unstated edge, an edge below break-even, and an edge too faint
to detect in the window actually available.

The arithmetic is not reimplemented in the gate (it imports `Power` from
`trade_power.py`), so it is not reimplemented here either — the figures below
were re-derived by hand against the same formulas and are pinned as constants.
"""

from __future__ import annotations

import importlib.util
import sys
from decimal import Decimal
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "research" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


gate = _load("edge_gate")


# --- step 1: no number is itself an answer ---------------------------------


def test_an_unstated_edge_fails_at_step_one() -> None:
    """The most common real failure. 'It should be profitable' is not an edge,
    and the gate must not quietly assume a number to get past it."""
    result = gate.check(claimed_gross_edge_pct=None, size_usd=10)
    assert result.verdict == "FAIL"
    assert result.steps[0]["step"] == 1
    assert result.steps[0]["passed"] is False
    assert result.claimed_gross_edge_pct is None


def test_a_stated_edge_passes_step_one() -> None:
    result = gate.check(claimed_gross_edge_pct=0.5, size_usd=10)
    assert result.steps[0]["passed"] is True


# --- step 2: break-even is size-dependent ----------------------------------


def test_break_even_is_higher_at_smaller_size() -> None:
    """Fixed cost does not scale down. This is why $5 is harder than $10,
    and it is arithmetic, not opinion."""
    at_five = gate.check(claimed_gross_edge_pct=1.0, size_usd=5).break_even_pct
    at_ten = gate.check(claimed_gross_edge_pct=1.0, size_usd=10).break_even_pct
    assert at_five == pytest.approx(0.254, abs=0.001)
    assert at_ten == pytest.approx(0.127, abs=0.001)
    assert at_five > at_ten


def test_an_edge_below_break_even_fails_and_stops() -> None:
    """Below break-even the gate must not go on to discuss sample size —
    no sample size fixes a negative expectancy, and implying otherwise
    would invite 'just run it longer'."""
    result = gate.check(claimed_gross_edge_pct=0.1, size_usd=5)
    assert result.verdict == "FAIL"
    step2 = next(s for s in result.steps if s["step"] == 2)
    assert step2["passed"] is False
    assert result.trades_needed is None
    assert not any(s["step"] == 3 for s in result.steps), (
        "step 3 must not be reported once step 2 has failed"
    )


def test_an_edge_exactly_at_break_even_does_not_pass() -> None:
    """Exactly break-even is zero expectancy, not a marginal pass."""
    result = gate.check(claimed_gross_edge_pct=0.127, size_usd=10)
    step2 = next(s for s in result.steps if s["step"] == 2)
    assert step2["passed"] is False


# --- step 3: detection floor -----------------------------------------------


def test_a_thin_edge_clears_break_even_but_cannot_be_detected() -> None:
    """The case the gate exists for. 0.3% at $5 is genuinely positive after
    costs and still needs ~3,355 round trips — 48x what a 30-day window
    yields. Re-derived by hand: net = 5*0.003 - 0.0127 = 0.0023;
    sigma = 5*0.00951 = 0.04755; n = 7.8489*(0.04755/0.0023)^2 = 3354.7."""
    result = gate.check(claimed_gross_edge_pct=0.3, size_usd=5)
    step2 = next(s for s in result.steps if s["step"] == 2)
    step3 = next(s for s in result.steps if s["step"] == 3)
    assert step2["passed"] is True, "0.3% is above the 0.254% hurdle at $5"
    assert step3["passed"] is False
    assert result.trades_needed == pytest.approx(3354.7, rel=0.01)
    assert result.verdict == "FAIL"


def test_a_healthy_edge_reaches_step_four() -> None:
    """0.5% at $10 needs ~51 round trips against 70.5 available.
    Re-derived: net = 10*0.005 - 0.0127 = 0.0373; sigma = 0.0951;
    n = 7.8489*(0.0951/0.0373)^2 = 51.0."""
    result = gate.check(claimed_gross_edge_pct=0.5, size_usd=10)
    assert result.trades_needed == pytest.approx(51.0, rel=0.01)
    assert result.trades_available == pytest.approx(70.5, rel=0.01)
    step3 = next(s for s in result.steps if s["step"] == 3)
    assert step3["passed"] is True


def test_a_short_window_fails_an_otherwise_fine_edge() -> None:
    """Same edge, less time. Viability is a property of the test as well as
    the strategy — this is the part people skip."""
    result = gate.check(claimed_gross_edge_pct=0.5, size_usd=10, window_days=5)
    step3 = next(s for s in result.steps if s["step"] == 3)
    assert step3["passed"] is False


def test_the_replication_minimum_is_enforced_at_nineteen() -> None:
    """Raised from 12 on 2026-09-16 because 12 sat below this project's own
    detection floor. A window yielding fewer than 19 pooled trades fails even
    when the edge is large enough to need fewer."""
    assert gate.REPLICATION_MIN_POOLED_TRADES == 19
    # 5% edge needs very few trades, but 4 days at 2.35/day yields only 9.4.
    result = gate.check(claimed_gross_edge_pct=5.0, size_usd=10,
                        window_days=4, trades_per_day=2.35)
    step3 = next(s for s in result.steps if s["step"] == 3)
    assert result.trades_needed < result.trades_available, (
        "precondition: the edge itself is detectable in this few trades"
    )
    assert step3["passed"] is False, (
        "but the replication rule's pooled minimum must still bind"
    )
    assert "19" in step3["detail"]


# --- step 4: the gate must admit what it cannot decide ----------------------


def test_step_four_is_reported_as_undecided_not_passed() -> None:
    """A gate that fabricates its hardest step is worse than one that admits
    the gap. Step 4 needs real bars; this must never silently read as a pass."""
    result = gate.check(claimed_gross_edge_pct=0.5, size_usd=10)
    step4 = next(s for s in result.steps if s["step"] == 4)
    assert step4["passed"] is None
    assert "edge_budget.py" in step4["detail"]
    assert result.verdict == "INCOMPLETE"
    assert result.verdict != "PASS"


def test_incomplete_is_not_sold_as_permission() -> None:
    result = gate.check(claimed_gross_edge_pct=0.5, size_usd=10)
    assert "never evidence an edge exists" in result.summary


# --- shape ------------------------------------------------------------------


def test_verdict_serialises_to_json() -> None:
    import json

    payload = json.loads(gate.check(claimed_gross_edge_pct=0.5).to_json())
    assert payload["verdict"] in {"PASS", "FAIL", "INCOMPLETE"}
    assert {"steps", "break_even_pct", "summary"} <= set(payload)


def test_the_gate_does_not_reimplement_the_arithmetic() -> None:
    """One gate, one implementation — the same principle that rejected a
    pasted validation_gate.py. If this ever stops importing Power, the two
    copies will drift and nobody will know which is right."""
    import inspect

    source = inspect.getsource(gate)
    assert "Power = _tp.Power" in source
    assert "Z_SQUARED = _tp.Z_SQUARED" in source

    # Strip comments and docstring prose before looking for a re-typed
    # constant: the value is legitimately *discussed* in a comment explaining
    # why the replication minimum is 19, and that mention is not a second
    # implementation. Only executable lines count.
    code_lines = [
        line.split("#", 1)[0]
        for line in source.splitlines()
        if not line.lstrip().startswith("#")
    ]
    code = "\n".join(code_lines)
    assert "7.8489" not in code, (
        "Z-squared must come from trade_power.py, not be re-typed in code here"
    )
    assert "0.0127" not in code, (
        "the fixed cost must come from trade_power.py too"
    )
