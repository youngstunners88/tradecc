"""Alerting must be silent when unconfigured, redacted when it sends, and
must never raise into a caller managing a position."""

from __future__ import annotations

import logging

import pytest

from core.alerts import Alert, Alerts, alerts_configured, configure_alerts, get_alerts
from core.logging import register_secret


class Recorder:
    def __init__(self) -> None:
        self.sent: list[Alert] = []

    def send(self, alert: Alert) -> None:
        self.sent.append(alert)


class Exploding:
    def send(self, alert: Alert) -> None:
        raise RuntimeError("mail provider down")


def an_alert(subject: str = "subject", body: str = "body") -> Alert:
    return Alert(subject, body, "gate.state_changed")


def test_unconfigured_alerts_report_nothing_to_retry():
    assert Alerts().send(an_alert()) is True


def test_configured_sink_receives_the_alert():
    recorder = Recorder()
    assert Alerts(recorder).send(an_alert()) is True
    assert [a.subject for a in recorder.sent] == ["subject"]


def test_delivery_failure_is_reported_not_raised():
    """A mail provider being down must not interrupt trading, but it also
    must not be mistaken for a delivered alert."""
    assert Alerts(Exploding()).send(an_alert()) is False


def test_enabled_reflects_whether_a_sink_exists():
    assert Alerts().enabled is False
    assert Alerts(Recorder()).enabled is True


def test_registered_secret_is_masked_before_it_reaches_the_sink():
    """The alert body travels off-box, so it goes through the same redaction
    path as the log rather than a second implementation of it."""
    register_secret("super-secret-key-value")
    recorder = Recorder()
    Alerts(recorder).send(an_alert(body="key is super-secret-key-value here"))
    assert "super-secret-key-value" not in recorder.sent[0].body


def test_key_shaped_context_is_masked_in_the_logged_record():
    """Context fields go to the log, not to the sink. They still travel the
    redaction path, so a key-shaped field is masked there too."""
    from core.logging import REDACTED

    captured: dict = {}

    class Capturing(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            captured.update(record.__dict__)

    handler = Capturing()
    alert_logger = logging.getLogger("tradecc.alerts")
    alert_logger.addHandler(handler)
    try:
        Alerts(Recorder()).send(an_alert(), private_key="abcdef123456", size_usd=10)
    finally:
        alert_logger.removeHandler(handler)

    assert captured["private_key"] == REDACTED
    assert captured["size_usd"] == 10


def test_configure_and_get_round_trip():
    recorder = Recorder()
    try:
        configure_alerts(recorder)
        assert get_alerts().enabled is True
        get_alerts().send(an_alert())
        assert len(recorder.sent) == 1
    finally:
        configure_alerts(None)
    assert get_alerts().enabled is False


@pytest.mark.parametrize(
    "env,expected",
    [
        ({}, False),
        ({"AGENTMAIL_API_KEY": "k"}, False),
        ({"AGENTMAIL_API_KEY": "k", "AGENTMAIL_FROM": "a@b.c"}, False),
        ({"AGENTMAIL_API_KEY": "k", "AGENTMAIL_FROM": "a@b.c", "AGENTMAIL_TO": "d@e.f"}, True),
    ],
)
def test_alerts_configured_requires_all_three(env, expected):
    assert alerts_configured(env) is expected
