"""The watcher must alert on every gate state change, stay silent otherwise,
and never be able to make the gate more permissive."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from core.alerts import Alert, Alerts
from core.gate import GateResult
from core.gate_watch import (
    FAILURES_CHANGED,
    FIRST_OBSERVATION,
    RELOCKED,
    UNLOCKED,
    GateWatcher,
)

AT = datetime(2026, 9, 13, 12, 0, tzinfo=timezone.utc)


class Recorder:
    def __init__(self) -> None:
        self.sent: list[Alert] = []

    def send(self, alert: Alert) -> None:
        self.sent.append(alert)


class Exploding:
    def send(self, alert: Alert) -> None:
        raise RuntimeError("mail provider down")


def watcher(tmp_path: Path, sink=None) -> GateWatcher:
    return GateWatcher(tmp_path / "state", Alerts(sink))


LOCKED = GateResult(False, ("net_expectancy_usd missing or not a number",))
UNLOCKED_RESULT = GateResult(True, ())
FINGERPRINT_BAD = GateResult(
    False, ("configuration changed since approval — 'risk' differs: re-validate",)
)


def test_first_observation_alerts(tmp_path):
    recorder = Recorder()
    transition = watcher(tmp_path, recorder).observe(LOCKED, AT)
    assert transition is not None
    assert transition.kind == FIRST_OBSERVATION
    assert len(recorder.sent) == 1


def test_unchanged_gate_is_silent(tmp_path):
    recorder = Recorder()
    w = watcher(tmp_path, recorder)
    w.observe(LOCKED, AT)
    assert w.observe(LOCKED, AT + timedelta(minutes=5)) is None
    assert len(recorder.sent) == 1, "a steady gate must not send a second email"


def test_locked_to_unlocked_alerts(tmp_path):
    recorder = Recorder()
    w = watcher(tmp_path, recorder)
    w.observe(LOCKED, AT)
    transition = w.observe(UNLOCKED_RESULT, AT + timedelta(minutes=5))
    assert transition is not None
    assert transition.kind == UNLOCKED
    assert transition.is_urgent
    assert "UNLOCKED" in recorder.sent[-1].subject


def test_unlocked_to_locked_alerts(tmp_path):
    recorder = Recorder()
    w = watcher(tmp_path, recorder)
    w.observe(UNLOCKED_RESULT, AT)
    transition = w.observe(LOCKED, AT + timedelta(minutes=5))
    assert transition is not None
    assert transition.kind == RELOCKED
    assert transition.is_urgent
    assert "RE-LOCKED" in recorder.sent[-1].subject


def test_different_failures_while_still_locked_alerts(tmp_path):
    recorder = Recorder()
    w = watcher(tmp_path, recorder)
    w.observe(LOCKED, AT)
    other = GateResult(False, ("trade_count missing or not an integer",))
    transition = w.observe(other, AT + timedelta(minutes=5))
    assert transition is not None
    assert transition.kind == FAILURES_CHANGED


def test_fingerprint_mismatch_is_flagged_and_urgent(tmp_path):
    recorder = Recorder()
    transition = watcher(tmp_path, recorder).observe(FINGERPRINT_BAD, AT)
    assert transition is not None
    assert transition.fingerprint_mismatch
    assert transition.is_urgent, "a mismatch is urgent even when the gate was already locked"
    assert "FINGERPRINT MISMATCH" in recorder.sent[-1].subject


def test_failed_delivery_does_not_advance_the_snapshot(tmp_path):
    """An alert that failed to send is not an alert that happened: the next
    evaluation must detect the same transition and try again."""
    w = GateWatcher(tmp_path / "state", Alerts(Exploding()))
    assert w.observe(LOCKED, AT) is not None
    assert not w.path.exists(), "snapshot must not advance past an undelivered alert"

    recorder = Recorder()
    retry = GateWatcher(tmp_path / "state", Alerts(recorder))
    assert retry.observe(LOCKED, AT + timedelta(minutes=5)) is not None
    assert len(recorder.sent) == 1, "the missed alert must be retried"


def test_snapshot_advances_when_alerts_are_switched_off(tmp_path):
    """With no sink there is nothing to retry, so the state must still advance
    or an unconfigured bot would re-detect the same transition forever."""
    w = GateWatcher(tmp_path / "state", Alerts(None))
    assert w.observe(LOCKED, AT) is not None
    assert w.observe(LOCKED, AT + timedelta(minutes=5)) is None


def test_corrupt_snapshot_alerts_rather_than_going_quiet(tmp_path):
    recorder = Recorder()
    w = watcher(tmp_path, recorder)
    w.observe(LOCKED, AT)
    w.path.write_text("{not json")
    transition = w.observe(LOCKED, AT + timedelta(minutes=5))
    assert transition is not None
    assert transition.kind == FIRST_OBSERVATION


def test_observing_cannot_change_the_verdict(tmp_path):
    """The watcher reads a GateResult and returns a transition. It has no path
    by which a caller could route a decision through it."""
    result = GateResult(False, ("net_expectancy_usd missing or not a number",))
    watcher(tmp_path, Recorder()).observe(result, AT)
    assert result.unlocked is False
    assert result.failures == ("net_expectancy_usd missing or not a number",)
    assert not hasattr(GateWatcher, "unlock")


def test_naive_timestamp_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="timezone-aware"):
        watcher(tmp_path, Recorder()).observe(LOCKED, datetime(2026, 9, 13, 12, 0))


def test_body_lists_current_failures_and_what_cleared(tmp_path):
    recorder = Recorder()
    w = watcher(tmp_path, recorder)
    w.observe(GateResult(False, ("alpha failed", "beta failed")), AT)
    w.observe(GateResult(False, ("beta failed",)), AT + timedelta(minutes=5))
    body = recorder.sent[-1].body
    assert "beta failed" in body
    assert "No longer failing:" in body
    assert "alpha failed" in body.split("No longer failing:")[1]


def test_body_states_that_nothing_was_sent_on_chain(tmp_path):
    recorder = Recorder()
    watcher(tmp_path, recorder).observe(UNLOCKED_RESULT, AT)
    assert "nothing has been sent on chain" in recorder.sent[-1].body
