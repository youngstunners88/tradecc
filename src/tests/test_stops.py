from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from core.types import Position
from risk.stops import StopAction, evaluate_stops
from tests.conftest import TOKEN


def position(entry: str = "100", size: str = "10") -> Position:
    return Position(
        token_mint=TOKEN,
        entry_price=Decimal(entry),
        size_usd=Decimal(size),
        opened_at=datetime(2026, 9, 9, tzinfo=timezone.utc),
    )


def test_holds_inside_bounds(risk_config):
    evaluation = evaluate_stops(position(), Decimal("102"), risk_config)

    assert evaluation.action is StopAction.HOLD
    assert not evaluation.should_close


def test_stop_loss_triggers_at_threshold(risk_config):
    evaluation = evaluate_stops(position(), Decimal("95"), risk_config)  # -5%

    assert evaluation.action is StopAction.STOP_LOSS
    assert evaluation.should_close


def test_stop_loss_triggers_beyond_threshold(risk_config):
    evaluation = evaluate_stops(position(), Decimal("80"), risk_config)  # -20%

    assert evaluation.action is StopAction.STOP_LOSS
    assert evaluation.pnl_usd == Decimal("-2")


def test_take_profit_triggers_at_threshold(risk_config):
    evaluation = evaluate_stops(position(), Decimal("110"), risk_config)  # +10%

    assert evaluation.action is StopAction.TAKE_PROFIT
    assert evaluation.pnl_usd == Decimal("1")


def test_just_inside_stop_loss_still_holds(risk_config):
    evaluation = evaluate_stops(position(), Decimal("95.01"), risk_config)

    assert evaluation.action is StopAction.HOLD


def test_pnl_is_exact_with_decimals(risk_config):
    evaluation = evaluate_stops(position(entry="0.30"), Decimal("0.33"), risk_config)

    # Floats would give 9.999999999999998 here.
    assert evaluation.pnl_pct == Decimal("10")
    assert evaluation.action is StopAction.TAKE_PROFIT


def test_rejects_non_positive_price(risk_config):
    with pytest.raises(ValueError):
        evaluate_stops(position(), Decimal("0"), risk_config)
