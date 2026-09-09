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
