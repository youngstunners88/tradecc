"""The live gate must fail closed. No input should unlock it by accident."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.gate import evaluate_live_gate

VALID_GATE = {
    "paper_started_at": "2026-01-01T00:00:00+00:00",
    "paper_ended_at": "2026-02-15T00:00:00+00:00",
    "threshold_set_at": "2025-12-28T00:00:00+00:00",
    "max_drawdown_threshold_pct": 15,
    "observed_max_drawdown_pct": 8.4,
    "net_expectancy_usd": 1.25,
    "approved_by": "chris",
    "approved_at": "2026-02-16T09:00:00+00:00",
}


def write_gate(path: Path, **overrides) -> Path:
    data = {**VALID_GATE, **overrides}
    for key, value in list(data.items()):
        if value is None:
            del data[key]
    path.write_text(json.dumps(data))
    return path


def test_fully_satisfied_gate_unlocks(tmp_path):
    result = evaluate_live_gate(write_gate(tmp_path / "gate.json"))

    assert result.unlocked


def test_missing_file_is_locked(tmp_path):
    result = evaluate_live_gate(tmp_path / "nope.json")

    assert not result.unlocked
    assert "never been unlocked" in result.describe()


def test_malformed_json_is_locked(tmp_path):
    path = tmp_path / "gate.json"
    path.write_text("{ not json at all")

    assert not evaluate_live_gate(path).unlocked


def test_non_object_json_is_locked(tmp_path):
    path = tmp_path / "gate.json"
    path.write_text("[1, 2, 3]")

    assert not evaluate_live_gate(path).unlocked


def test_empty_object_is_locked(tmp_path):
    path = tmp_path / "gate.json"
    path.write_text("{}")

    assert not evaluate_live_gate(path).unlocked


def test_short_paper_run_is_locked(tmp_path):
    result = evaluate_live_gate(
        write_gate(tmp_path / "gate.json", paper_ended_at="2026-01-20T00:00:00+00:00")
    )

    assert not result.unlocked
    assert "needs at least 30" in result.describe()


def test_drawdown_over_threshold_is_locked(tmp_path):
    result = evaluate_live_gate(
        write_gate(tmp_path / "gate.json", observed_max_drawdown_pct=22.5)
    )

    assert not result.unlocked
    assert "exceeds threshold" in result.describe()


def test_threshold_set_after_run_started_is_locked(tmp_path):
    """A threshold picked after seeing results is not a gate."""
    result = evaluate_live_gate(
        write_gate(tmp_path / "gate.json", threshold_set_at="2026-02-01T00:00:00+00:00")
    )

    assert not result.unlocked
    assert "does not constitute a gate" in result.describe()


@pytest.mark.parametrize("expectancy", [0, -0.5, -12])
def test_non_positive_expectancy_is_locked(tmp_path, expectancy):
    result = evaluate_live_gate(
        write_gate(tmp_path / "gate.json", net_expectancy_usd=expectancy)
    )

    assert not result.unlocked
    assert "not positive" in result.describe()


@pytest.mark.parametrize("field", ["approved_by", "approved_at"])
def test_missing_human_approval_is_locked(tmp_path, field):
    result = evaluate_live_gate(write_gate(tmp_path / "gate.json", **{field: None}))

    assert not result.unlocked


def test_blank_approver_is_locked(tmp_path):
    result = evaluate_live_gate(write_gate(tmp_path / "gate.json", approved_by="   "))

    assert not result.unlocked


@pytest.mark.parametrize(
    "field",
    ["paper_started_at", "paper_ended_at", "max_drawdown_threshold_pct", "net_expectancy_usd"],
)
def test_any_missing_required_field_is_locked(tmp_path, field):
    result = evaluate_live_gate(write_gate(tmp_path / "gate.json", **{field: None}))

    assert not result.unlocked


def test_all_failures_are_reported_together(tmp_path):
    result = evaluate_live_gate(
        write_gate(
            tmp_path / "gate.json",
            paper_ended_at="2026-01-05T00:00:00+00:00",
            net_expectancy_usd=-3,
            approved_by=None,
        )
    )

    assert not result.unlocked
    assert len(result.failures) >= 3


# --- Non-finite numbers and mixed-awareness timestamps.
#
# All four inputs below used to defeat the fail-closed contract: two by
# raising an uncaught exception out of the module, two by quietly unlocking.
# json.loads parses the bare literals NaN/Infinity by default, so none of
# these requires a hand-crafted parser to produce.


def test_infinite_drawdown_threshold_does_not_unlock(tmp_path):
    """Infinity as a threshold satisfied `observed > threshold` at any
    observed drawdown — a 99% drawdown passed a gate that claimed to cap it."""
    path = tmp_path / "gate.json"
    path.write_text(
        json.dumps({**VALID_GATE, "observed_max_drawdown_pct": 99}).replace(
            '"max_drawdown_threshold_pct": 15', '"max_drawdown_threshold_pct": Infinity'
        )
    )
    result = evaluate_live_gate(path)
    assert not result.unlocked
    assert any("max_drawdown_threshold_pct" in f for f in result.failures)


def test_nan_expectancy_is_locked_not_a_crash(tmp_path):
    """Decimal('NaN') raises InvalidOperation from `expectancy <= 0`."""
    path = tmp_path / "gate.json"
    path.write_text(json.dumps(VALID_GATE).replace('"net_expectancy_usd": 1.25',
                                                   '"net_expectancy_usd": NaN'))
    result = evaluate_live_gate(path)
    assert not result.unlocked
    assert any("net_expectancy_usd" in f for f in result.failures)


def test_infinite_expectancy_does_not_unlock(tmp_path):
    path = tmp_path / "gate.json"
    path.write_text(json.dumps(VALID_GATE).replace('"net_expectancy_usd": 1.25',
                                                   '"net_expectancy_usd": Infinity'))
    assert not evaluate_live_gate(path).unlocked


def test_mixed_naive_and_aware_timestamps_do_not_crash(tmp_path):
    """A naive paper_ended_at against an aware paper_started_at raised
    TypeError straight out of the module. Naive is now read as UTC."""
    result = evaluate_live_gate(
        write_gate(tmp_path / "gate.json", paper_ended_at="2026-02-15T00:00:00")
    )
    assert isinstance(result.unlocked, bool)
    assert result.unlocked, result.failures


def test_naive_timestamps_throughout_still_evaluate(tmp_path):
    result = evaluate_live_gate(
        write_gate(
            tmp_path / "gate.json",
            paper_started_at="2026-01-01T00:00:00",
            paper_ended_at="2026-02-15T00:00:00",
            threshold_set_at="2025-12-28T00:00:00",
            approved_at="2026-02-16T09:00:00",
        )
    )
    assert result.unlocked, result.failures


def test_boolean_is_not_a_number(tmp_path):
    """JSON `true` must not become Decimal(1) and satisfy a numeric check."""
    result = evaluate_live_gate(write_gate(tmp_path / "gate.json", net_expectancy_usd=True))
    assert not result.unlocked
