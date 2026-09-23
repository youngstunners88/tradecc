import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from check_entrypoints import check, missing_entrypoints, scripts_from_package_json
from clock import (
    MIN_RESOLVED_DEFAULT, ClockError, Decision, blockers, status_of,
    verify_not_restarted,
)

DAY = 86_400.0


def decisions(n, *, start=0.0, step=1.0, resolved=0):
    return [
        Decision(id=f"d{i}", at=start + i * step, outcome=(True if i < resolved else None))
        for i in range(n)
    ]


# --- the clock has not started --------------------------------------------

def test_empty_journal_reports_NOT_STARTED_not_zero_days_elapsed():
    """The distinction that matters: 'no evidence' is not 'no time passed'."""
    s = status_of([], required_days=30, now=999 * DAY)
    assert s.started is False
    assert s.satisfied is False
    assert "NOT STARTED" in blockers(s)[0]


def test_not_started_blocker_names_the_actual_cause():
    # The real Hydra cause: an advertised script whose file did not exist.
    assert "entry point" in blockers(status_of([], required_days=30, now=0))[0]


# --- derivation ------------------------------------------------------------

def test_clock_starts_at_the_EARLIEST_decision():
    s = status_of(decisions(3, start=10 * DAY, step=DAY), required_days=30, now=20 * DAY)
    assert s.started_at == 10 * DAY
    assert s.elapsed_days == pytest.approx(10.0)


def test_a_later_decision_does_not_move_the_start():
    early = decisions(1, start=0.0)
    late = early + [Decision("dz", at=5 * DAY)]
    assert status_of(late, required_days=30, now=5 * DAY).started_at == 0.0


def test_refuses_a_decision_timestamped_in_the_future():
    """Clock source and decision source disagreeing invalidates every elapsed
    figure, so it raises rather than reporting a negative age."""
    with pytest.raises(ClockError, match="backwards"):
        status_of(decisions(1, start=100 * DAY), required_days=30, now=0)


def test_refuses_a_zero_day_minimum():
    with pytest.raises(ClockError, match="not a gate"):
        status_of([], required_days=0, now=0)


def test_refuses_a_zero_sample_minimum():
    with pytest.raises(ClockError, match="vacuously"):
        status_of([], required_days=30, now=0, min_resolved=0)


# --- the two blockers are independent --------------------------------------

def test_days_satisfied_does_NOT_satisfy_the_gate_alone():
    s = status_of(decisions(3, start=0), required_days=30, now=100 * DAY)
    assert s.days_satisfied is True
    assert s.sample_satisfied is False
    assert s.satisfied is False


def test_sample_satisfied_does_NOT_satisfy_the_gate_alone():
    s = status_of(decisions(200, resolved=200), required_days=30, now=DAY)
    assert s.sample_satisfied is True
    assert s.days_satisfied is False
    assert s.satisfied is False


def test_both_satisfied_passes():
    s = status_of(decisions(200, resolved=200), required_days=30, now=40 * DAY)
    assert s.satisfied is True


def test_shortening_the_calendar_does_not_unlock_the_gate():
    """The tempting shortcut, shown not to work.

    Cutting 30 days to 2 moves the calendar check and leaves the sample-size
    check exactly where it was, because a shorter window does not produce more
    resolved outcomes. The gate stays shut and the safety margin is gone.
    """
    thirty = status_of(decisions(5, resolved=5), required_days=30, now=3 * DAY)
    two = status_of(decisions(5, resolved=5), required_days=2, now=3 * DAY)
    assert two.days_satisfied is True and thirty.days_satisfied is False
    assert two.satisfied is False          # still shut
    assert two.sample_satisfied is False   # and for the same reason as before


def test_blockers_lists_both_causes_separately():
    b = blockers(status_of(decisions(3), required_days=30, now=DAY))
    assert len(b) == 2
    assert any("days" in x for x in b)
    assert any("RESOLVED" in x for x in b)


def test_pending_decisions_do_not_count_as_resolved():
    s = status_of(decisions(200, resolved=0), required_days=30, now=40 * DAY)
    assert s.decisions == 200
    assert s.resolved == 0
    assert s.satisfied is False


def test_min_resolved_default_is_the_derived_97():
    assert MIN_RESOLVED_DEFAULT == 97


# --- durability proof ------------------------------------------------------

def test_verify_not_restarted_accepts_a_durable_run():
    before = status_of(decisions(3), required_days=30, now=DAY)
    after = status_of(decisions(5), required_days=30, now=2 * DAY)
    verify_not_restarted(before, after)


def test_verify_not_restarted_CATCHES_a_volatile_store():
    """The whole point. One run cannot tell a durable store from a dict."""
    before = status_of(decisions(3, start=0), required_days=30, now=DAY)
    after = status_of(decisions(3, start=50 * DAY), required_days=30, now=51 * DAY)
    with pytest.raises(ClockError, match="RESTARTED"):
        verify_not_restarted(before, after)


def test_verify_not_restarted_catches_a_second_run_that_wrote_nothing():
    s = status_of(decisions(3), required_days=30, now=DAY)
    with pytest.raises(ClockError, match="wrote nothing"):
        verify_not_restarted(s, s)


def test_verify_not_restarted_catches_a_clock_that_went_back_to_NOT_STARTED():
    before = status_of(decisions(3), required_days=30, now=DAY)
    after = status_of([], required_days=30, now=2 * DAY)
    with pytest.raises(ClockError, match="NOT STARTED"):
        verify_not_restarted(before, after)


def test_verify_not_restarted_refuses_to_compare_from_an_unstarted_clock():
    empty = status_of([], required_days=30, now=0)
    with pytest.raises(ClockError, match="cannot show anything"):
        verify_not_restarted(empty, status_of(decisions(3), required_days=30, now=DAY))


# --- entry points ----------------------------------------------------------

def write_pkg(tmp_path, scripts):
    p = tmp_path / "package.json"
    p.write_text(json.dumps({"scripts": scripts}))
    return p


def test_detects_an_advertised_script_whose_file_is_missing(tmp_path):
    # The exact Hydra failure: four advertised scripts, none of them written.
    pkg = write_pkg(tmp_path, {"hunt": "tsx scripts/hunt_once.ts"})
    ok, report = check(pkg)
    assert ok is False
    assert "hunt_once.ts NOT FOUND" in report


def test_passes_when_the_file_exists(tmp_path):
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "hunt_once.ts").write_text("//")
    ok, report = check(write_pkg(tmp_path, {"hunt": "tsx scripts/hunt_once.ts"}))
    assert ok is True
    assert "all present" in report


def test_a_GLOB_that_matches_is_not_reported_missing(tmp_path):
    """A checker that cries wolf gets ignored, and an ignored checker is none."""
    (tmp_path / "packages" / "a" / "tests").mkdir(parents=True)
    (tmp_path / "packages" / "a" / "tests" / "x.test.ts").write_text("//")
    ok, _ = check(write_pkg(tmp_path, {"test": "node --test packages/*/tests/*.test.ts"}))
    assert ok is True


def test_a_GLOB_that_matches_NOTHING_is_reported(tmp_path):
    ok, report = check(write_pkg(tmp_path, {"test": "node --test packages/*/tests/*.test.ts"}))
    assert ok is False
    assert "NOT FOUND" in report


def test_a_script_naming_no_file_is_not_a_failure(tmp_path):
    ok, _ = check(write_pkg(tmp_path, {"build": "pnpm -r build"}))
    assert ok is True


def test_an_empty_manifest_is_VACUOUS_not_a_pass(tmp_path):
    ok, report = check(write_pkg(tmp_path, {}))
    assert ok is False
    assert "VACUOUS" in report


def test_extracts_the_file_from_a_command_with_flags(tmp_path):
    entries = scripts_from_package_json(
        write_pkg(tmp_path, {"hunt": "node --experimental-strip-types scripts/h.ts --blocks 5"})
    )
    assert entries[0].file == "scripts/h.ts"
