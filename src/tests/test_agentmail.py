"""AgentMail delivery — offline, against a local recording transport.

A local recorder rather than an extension of `FakeTransport`: that class is
shared by the provider suites and records only (method, url), and widening it
to capture headers has collided with an existing subclass before.
"""

from __future__ import annotations

import json

import pytest

from core.alerts import Alert
from core.rate_limit import RateLimiter
from execution.http import ProviderError, ProviderHttpClient, RetryPolicy
from notify.agentmail import AgentMailSink, build_sink_from_env
from tests.test_http import response


class RecordingTransport:
    def __init__(self, *responses) -> None:
        self._queue = list(responses) or [response(200, {"id": "msg_1"})]
        self.calls: list[dict] = []

    def request(self, method, url, *, headers=None, body=None, timeout=None):
        self.calls.append(
            {"method": method, "url": url, "headers": dict(headers or {}), "body": body}
        )
        item = self._queue.pop(0) if self._queue else response(200, {"id": "msg_1"})
        if isinstance(item, Exception):
            raise item
        return item


def make_sink(transport, api_key: str = "am_live_key") -> AgentMailSink:
    return AgentMailSink(
        api_key=api_key,
        sender="bot@tradecc.test",
        recipient="chris@example.test",
        transport=transport,
        client=ProviderHttpClient(
            provider="agentmail",
            transport=transport,
            limiter=RateLimiter(1000, 60.0, name="agentmail"),
            retry=RetryPolicy(max_attempts=1),
        ),
    )


def an_alert() -> Alert:
    return Alert("[TradeCC] live gate UNLOCKED", "body text", "gate.state_changed")


def test_send_posts_the_alert_to_agentmail():
    transport = RecordingTransport()
    make_sink(transport).send(an_alert())

    call = transport.calls[0]
    assert call["method"] == "POST"
    payload = json.loads(call["body"])
    assert payload["subject"] == "[TradeCC] live gate UNLOCKED"
    assert payload["text"] == "body text"
    assert payload["to"] == ["chris@example.test"]
    assert payload["from"] == "bot@tradecc.test"


def test_api_key_travels_in_a_header_never_in_the_url():
    """Provider URLs get logged. A key in the query string is a key in the log."""
    transport = RecordingTransport()
    make_sink(transport).send(an_alert())

    call = transport.calls[0]
    assert call["headers"]["Authorization"] == "Bearer am_live_key"
    assert "am_live_key" not in call["url"]


def test_provider_error_surfaces_so_the_alerter_can_retry():
    """The sink must not swallow a failure — `Alerts.send` turns it into a
    False return, which is what keeps the snapshot from advancing."""
    transport = RecordingTransport(response(400, {"error": "bad request"}))
    with pytest.raises(ProviderError):
        make_sink(transport).send(an_alert())


def test_plain_http_base_url_is_rejected():
    with pytest.raises(ValueError, match="https"):
        AgentMailSink("k", "a@b.test", "c@d.test", base_url="http://api.agentmail.to")


def test_build_sink_from_env_needs_a_complete_configuration():
    assert build_sink_from_env({}) is None
    assert build_sink_from_env({"AGENTMAIL_API_KEY": "k"}) is None
    assert build_sink_from_env({"AGENTMAIL_API_KEY": "k", "AGENTMAIL_FROM": "a@b.test"}) is None

    sink = build_sink_from_env(
        {
            "AGENTMAIL_API_KEY": "k",
            "AGENTMAIL_FROM": "a@b.test",
            "AGENTMAIL_TO": "c@d.test",
        }
    )
    assert isinstance(sink, AgentMailSink)
