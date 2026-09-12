"""The risk engine is the single veto point. These tests are the proof."""

from __future__ import annotations

import json
from decimal import Decimal

import pytest

from core.types import Mode, RejectionCode
from risk.engine import RiskEngine
from tests.conftest import make_intent, make_quote
from tests.test_gate import VALID_GATE


@pytest.fixture
def engine(run_config, store) -> RiskEngine:
    return RiskEngine(run_config, store)


def live_config(run_config):
    """The same config, configured for live. A LIVE intent belongs to a
    live-configured engine; pairing a PAPER engine with a LIVE intent is the
    inconsistency `_check_live_gate` now refuses outright."""
    return run_config.model_copy(update={"mode": Mode.LIVE})


def test_approves_a_clean_intent(engine, now):
    assert engine.approve(make_intent(), now).approved


def test_blocks_on_slippage(engine, now):
    intent = make_intent(quote=make_quote(expected="100", worst_case="103"))

    decision = engine.approve(intent, now)

    assert not decision.approved
    assert RejectionCode.SLIPPAGE_EXCEEDED in decision.codes


def test_blocks_on_oversized_position(engine, now):
    decision = engine.approve(make_intent(size_usd="250"), now)

    assert not decision.approved
    assert RejectionCode.POSITION_SIZE_EXCEEDED in decision.codes


def test_blocks_once_circuit_breaker_trips(engine, now):
    assert engine.approve(make_intent(), now).approved

    engine.record_realized_pnl(Decimal("-20"), now)

    decision = engine.approve(make_intent(), now)
    assert not decision.approved
    assert RejectionCode.CIRCUIT_BREAKER_TRIPPED in decision.codes


def test_reports_every_reason_not_just_the_first(engine, now):
    engine.record_realized_pnl(Decimal("-30"), now)
    intent = make_intent(size_usd="900", quote=make_quote(expected="100", worst_case="140"))

    decision = engine.approve(intent, now)

    assert not decision.approved
    assert RejectionCode.CIRCUIT_BREAKER_TRIPPED in decision.codes
    assert RejectionCode.POSITION_SIZE_EXCEEDED in decision.codes
    assert RejectionCode.SLIPPAGE_EXCEEDED in decision.codes


def test_risk_checks_apply_in_backtest_and_paper_too(engine, now):
    """Simulated modes run the same checks, or the paper run proves nothing."""
    for mode in (Mode.BACKTEST, Mode.PAPER):
        intent = make_intent(mode=mode, quote=make_quote(expected="100", worst_case="110"))

        assert not engine.approve(intent, now).approved


def test_live_mode_refused_when_gate_file_absent(engine, now):
    decision = engine.approve(make_intent(mode=Mode.LIVE), now)

    assert not decision.approved
    assert RejectionCode.LIVE_GATE_NOT_MET in decision.codes


def test_live_mode_refused_when_gate_unsatisfied(run_config, store, now):
    run_config.gate_file.write_text(
        json.dumps({**VALID_GATE, "paper_ended_at": "2026-01-03T00:00:00+00:00"})
    )
    engine = RiskEngine(run_config, store)

    decision = engine.approve(make_intent(mode=Mode.LIVE), now)

    assert not decision.approved
    assert RejectionCode.LIVE_GATE_NOT_MET in decision.codes


def test_live_mode_allowed_only_once_gate_is_fully_satisfied(run_config, store, now):
    run_config.gate_file.write_text(json.dumps(VALID_GATE))
    engine = RiskEngine(live_config(run_config), store)

    assert engine.approve(make_intent(mode=Mode.LIVE), now).approved


def test_paper_configured_engine_refuses_a_live_intent(run_config, store, now):
    """The gate used to be keyed on the caller-supplied intent.mode, so a
    paper-configured engine would evaluate — and could approve — a live
    trade whenever the gate file happened to be satisfied."""
    run_config.gate_file.write_text(json.dumps(VALID_GATE))
    engine = RiskEngine(run_config, store)  # configured PAPER

    decision = engine.approve(make_intent(mode=Mode.LIVE), now)

    assert not decision.approved
    assert RejectionCode.LIVE_GATE_NOT_MET in decision.codes


def test_live_configured_engine_refuses_an_intent_claiming_paper(run_config, store, now):
    """The dangerous direction: once signing exists, a live-configured
    process must not execute an intent that claims to be paper."""
    run_config.gate_file.write_text(json.dumps(VALID_GATE))
    engine = RiskEngine(live_config(run_config), store)

    decision = engine.approve(make_intent(mode=Mode.PAPER), now)

    assert not decision.approved
    assert RejectionCode.LIVE_GATE_NOT_MET in decision.codes


def test_satisfied_gate_does_not_bypass_other_risk_checks(run_config, store, now):
    """Unlocking live must not become a skeleton key for the rest of risk."""
    run_config.gate_file.write_text(json.dumps(VALID_GATE))
    engine = RiskEngine(run_config, store)
    engine.record_realized_pnl(Decimal("-25"), now)

    decision = engine.approve(make_intent(mode=Mode.LIVE), now)

    assert not decision.approved
    assert RejectionCode.CIRCUIT_BREAKER_TRIPPED in decision.codes


def test_stop_evaluation_is_exposed_through_the_engine(engine, run_config):
    from datetime import datetime, timezone

    from core.types import Position
    from risk.stops import StopAction
    from tests.conftest import TOKEN

    position = Position(
        token_mint=TOKEN,
        entry_price=Decimal("100"),
        size_usd=Decimal("10"),
        opened_at=datetime(2026, 9, 9, tzinfo=timezone.utc),
    )

    assert engine.evaluate_position(position, Decimal("90")).action is StopAction.STOP_LOSS


def test_tighter_config_limits_are_honoured(run_config, store, now):
    tightened_risk = run_config.risk.model_copy(update={"max_slippage_pct": Decimal("0.1")})
    engine = RiskEngine(run_config.model_copy(update={"risk": tightened_risk}), store)
    intent = make_intent(quote=make_quote(expected="100", worst_case="100.2"))  # 0.2%

    assert not engine.approve(intent, now).approved
