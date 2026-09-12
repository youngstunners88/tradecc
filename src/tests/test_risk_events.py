"""The risk engine must emit the PostHog events the schema promises."""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

import pytest

from core.telemetry import configure_telemetry
from core.types import Mode
from risk.engine import RiskEngine
from tests.conftest import make_intent, make_quote
from tests.test_gate import VALID_GATE


class FakeSink:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, Any]]] = []

    def capture(self, distinct_id: str, event: str, properties: dict[str, Any]) -> None:
        self.events.append((event, properties))

    def names(self) -> list[str]:
        return [name for name, _ in self.events]

    def properties_for(self, name: str) -> dict[str, Any]:
        return next(props for event, props in self.events if event == name)


@pytest.fixture
def sink():
    sink = FakeSink()
    configure_telemetry(sink=sink)
    yield sink
    configure_telemetry(sink=None, env={})


@pytest.fixture
def engine(run_config, store) -> RiskEngine:
    return RiskEngine(run_config, store)


def test_approved_trade_emits_no_rejection_events(engine, sink, now):
    engine.approve(make_intent(), now)

    assert sink.names() == []


def test_slippage_rejection_emits_risk_blocked(engine, sink, now):
    engine.approve(make_intent(quote=make_quote(expected="100", worst_case="105")), now)

    properties = sink.properties_for("risk.blocked")
    assert properties["reason"] == "slippage_exceeded"
    assert properties["attempted_size_usd"] == "10"


def test_daily_halt_emits_its_own_event(engine, sink, now):
    engine.record_realized_pnl(Decimal("-20"), now)

    properties = sink.properties_for("risk.daily_halt_triggered")
    assert properties["realized_loss_usd"] == "20"
    assert properties["threshold_usd"] == "20"


def test_live_gate_refusal_emits_gate_event(engine, sink, now):
    engine.approve(make_intent(mode=Mode.LIVE), now)

    assert "gate.live_mode_refused" in sink.names()
    assert "risk.blocked" not in sink.names()


def test_each_rejection_reason_gets_its_own_event(engine, sink, now):
    engine.record_realized_pnl(Decimal("-30"), now)
    sink.events.clear()

    engine.approve(
        make_intent(size_usd="900", quote=make_quote(expected="100", worst_case="140")), now
    )

    reasons = {props["reason"] for event, props in sink.events if event == "risk.blocked"}
    assert reasons == {"circuit_breaker_tripped", "position_size_exceeded", "slippage_exceeded"}


def test_unlocked_live_trade_emits_no_gate_refusal(run_config, store, sink, now):
    # Live-configured, because a LIVE intent on a PAPER-configured engine is
    # now refused outright — see test_paper_configured_engine_refuses_a_live
    # _intent in test_risk_engine.py.
    run_config.gate_file.write_text(json.dumps(VALID_GATE))
    live = run_config.model_copy(update={"mode": Mode.LIVE})

    RiskEngine(live, store).approve(make_intent(mode=Mode.LIVE), now)

    assert sink.names() == []
