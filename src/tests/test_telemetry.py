"""Telemetry must redact exactly like the logger, and never break trading."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest

from core.logging import REDACTED
from core.telemetry import Telemetry, configure_telemetry, get_telemetry, log_and_track

FAKE_KEY = "4NfMxKQ8bU1sTESTKEYnotarealsecret9xZq2"


class FakeSink:
    def __init__(self) -> None:
        self.events: list[tuple[str, str, dict[str, Any]]] = []

    def capture(self, distinct_id: str, event: str, properties: dict[str, Any]) -> None:
        self.events.append((distinct_id, event, properties))


class ExplodingSink:
    def capture(self, distinct_id: str, event: str, properties: dict[str, Any]) -> None:
        raise RuntimeError("posthog is down")


@pytest.fixture(autouse=True)
def reset_telemetry():
    yield
    configure_telemetry(sink=None, env={})


def test_disabled_by_default_when_no_api_key():
    configure_telemetry(env={})

    assert not get_telemetry().enabled


def test_enabled_when_api_key_present():
    configure_telemetry(env={"POSTHOG_API_KEY": "phc_fake"})

    assert get_telemetry().enabled


def test_sends_event_to_sink():
    sink = FakeSink()
    configure_telemetry(sink=sink)

    log_and_track("risk.blocked", reason="slippage_exceeded", token="So111")

    distinct_id, event, properties = sink.events[0]
    assert distinct_id == "tradecc-bot"
    assert event == "risk.blocked"
    assert properties["reason"] == "slippage_exceeded"


def test_sensitive_properties_are_redacted_before_sending():
    sink = FakeSink()
    configure_telemetry(sink=sink)

    log_and_track("trade.executed", private_key=FAKE_KEY, token="So111")

    _, _, properties = sink.events[0]
    assert properties["private_key"] == REDACTED
    assert FAKE_KEY not in str(properties)


def test_decimals_are_serialised_as_exact_strings():
    sink = FakeSink()
    configure_telemetry(sink=sink)

    log_and_track("trade.simulated", size_usd=Decimal("10.00"))

    _, _, properties = sink.events[0]
    assert properties["size_usd"] == "10.00"


def test_sink_failure_does_not_propagate():
    """PostHog being down is not a reason to stop managing a position."""
    configure_telemetry(sink=ExplodingSink())

    log_and_track("risk.daily_halt_triggered", realized_loss_usd=Decimal("20"))


@pytest.mark.parametrize(
    "field", ["wallet_address", "wallet_pubkey", "owner_address", "pubkey", "public_key"]
)
def test_wallet_identifiers_are_withheld_from_posthog(field):
    """Public on-chain data, but it links the whole trading history to one
    identity in a third party's system. It stays local."""
    sink = FakeSink()
    configure_telemetry(sink=sink)

    log_and_track("trade.executed", **{field: "7xKq...", "token": "So111"})

    _, _, properties = sink.events[0]
    assert field not in properties
    assert properties["token"] == "So111"


def test_withheld_fields_still_reach_the_local_log(caplog):
    configure_telemetry(sink=FakeSink())

    with caplog.at_level("INFO", logger="tradecc.telemetry"):
        log_and_track("trade.executed", wallet_address="7xKqABC")

    assert getattr(caplog.records[0], "wallet_address") == "7xKqABC"


def test_tx_signature_is_the_correlation_key_and_is_sent():
    sink = FakeSink()
    configure_telemetry(sink=sink)

    log_and_track("trade.executed", tx_signature="5Nx...", wallet_address="7xKq...")

    _, _, properties = sink.events[0]
    assert properties["tx_signature"] == "5Nx..."
    assert "wallet_address" not in properties


def test_distinct_id_is_the_bot_not_a_wallet():
    sink = FakeSink()
    configure_telemetry(sink=sink)

    log_and_track("trade.executed", token="So111")

    assert sink.events[0][0] == "tradecc-bot"


def test_disabled_telemetry_still_returns_redacted_payload():
    telemetry = Telemetry(sink=None)

    payload = telemetry.track("gate.live_mode_refused", api_key=FAKE_KEY)

    assert payload["api_key"] == REDACTED


def test_withheld_fields_are_dropped_at_every_depth():
    """A top-level-only filter let {"context": {"wallet_address": ...}}
    through, sending PostHog exactly the field the list exists to keep local."""
    from core.telemetry import for_telemetry

    out = for_telemetry(
        {
            "wallet_address": "top",
            "context": {"wallet_address": "nested", "ok": 1},
            "items": [{"pubkey": "deep", "keep": 2}],
        }
    )
    assert "wallet_address" not in out
    assert out["context"] == {"ok": 1}
    assert out["items"] == [{"keep": 2}]
