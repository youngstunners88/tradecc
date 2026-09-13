"""The daily circuit breaker must actually halt trading, and stay halted."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest

from core.types import RejectionCode
from risk.circuit_breaker import DailyCircuitBreaker
from risk.state import RiskStateStore


@pytest.fixture
def breaker(store: RiskStateStore) -> DailyCircuitBreaker:
    return DailyCircuitBreaker(Decimal("20"), store)


def test_approves_while_under_limit(breaker, now):
    breaker.record_realized_pnl(Decimal("-5"), now)
    assert breaker.check(now).approved


def test_halts_when_daily_loss_limit_reached(breaker, now):
    breaker.record_realized_pnl(Decimal("-20"), now)

    decision = breaker.check(now)

    assert not decision.approved
    assert RejectionCode.CIRCUIT_BREAKER_TRIPPED in decision.codes


def test_halts_on_accumulated_losses_not_just_one_trade(breaker, now):
    for _ in range(4):
        breaker.record_realized_pnl(Decimal("-5"), now)

    assert not breaker.check(now).approved


def test_halt_survives_restart(store, now):
    DailyCircuitBreaker(Decimal("20"), store).record_realized_pnl(Decimal("-25"), now)

    # A brand-new breaker over the same store is what a process restart looks like.
    restarted = DailyCircuitBreaker(Decimal("20"), RiskStateStore(store.path.parent))

    assert not restarted.check(now).approved


def test_halt_latches_even_if_later_profit_recovers_the_loss(breaker, now):
    breaker.record_realized_pnl(Decimal("-20"), now)
    breaker.record_realized_pnl(Decimal("+50"), now)

    # The day is over for trading purposes regardless of what happened after.
    assert not breaker.check(now).approved


def test_new_trading_day_clears_the_halt(breaker, now):
    breaker.record_realized_pnl(Decimal("-25"), now)
    assert not breaker.check(now).approved

    tomorrow = now + timedelta(days=1)

    assert breaker.check(tomorrow).approved
    assert breaker.state(tomorrow).realized_pnl_usd == Decimal("0")


def test_breach_noticed_on_check_is_persisted(store, now):
    breaker = DailyCircuitBreaker(Decimal("20"), store)
    breaker.record_realized_pnl(Decimal("-20"), now)

    breaker.check(now)

    assert store.load(now).halted is True


def test_remaining_budget_shrinks_with_losses_and_floors_at_zero(breaker, now):
    assert breaker.remaining_loss_budget_usd(now) == Decimal("20")

    breaker.record_realized_pnl(Decimal("-8"), now)
    assert breaker.remaining_loss_budget_usd(now) == Decimal("12")

    breaker.record_realized_pnl(Decimal("-50"), now)
    assert breaker.remaining_loss_budget_usd(now) == Decimal("0")


def test_profit_does_not_raise_the_loss_budget(breaker, now):
    breaker.record_realized_pnl(Decimal("+100"), now)

    # Winning early must not license a bigger loss later in the day.
    assert breaker.remaining_loss_budget_usd(now) == Decimal("20")


def test_rejects_non_positive_limit(store):
    with pytest.raises(ValueError):
        DailyCircuitBreaker(Decimal("0"), store)


def test_corrupt_state_file_halts_trading(store, now):
    """Fail closed. This previously returned a CLEAN day, which made
    truncating or deleting the file a way to clear a halt — the exact failure
    persistence exists to prevent."""
    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_text("{ not json")

    breaker = DailyCircuitBreaker(Decimal("20"), store)

    assert not breaker.check(now).approved
    assert "unreadable" in (breaker.state(now).halt_reason or "")


def test_a_halt_cannot_be_cleared_by_editing_halted_to_false(store, now):
    """Valid JSON, tampered field. The checksum no longer matches, so the
    edit reads as corruption and trading stays halted."""
    import json as _json

    breaker = DailyCircuitBreaker(Decimal("20"), store)
    breaker.record_realized_pnl(Decimal("-25"), now)
    assert not breaker.check(now).approved

    raw = _json.loads(store.path.read_text())
    assert raw["halted"] is True
    raw["halted"] = False
    raw["halt_reason"] = None
    store.path.write_text(_json.dumps(raw))  # checksum left stale

    assert not breaker.check(now).approved
    assert "checksum" in (breaker.state(now).halt_reason or "")


def test_a_file_with_no_checksum_halts(store, now):
    """State written by something other than this store is not trusted."""
    import json as _json
    from datetime import timezone

    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_text(
        _json.dumps(
            {
                "trading_day": now.astimezone(timezone.utc).date().isoformat(),
                "realized_pnl_usd": "0",
                "trade_count": 0,
                "halted": False,
                "halt_reason": None,
            }
        )
    )

    breaker = DailyCircuitBreaker(Decimal("20"), store)

    assert not breaker.check(now).approved
    assert "no checksum" in (breaker.state(now).halt_reason or "")


def test_non_finite_persisted_pnl_cannot_disable_the_breaker(tmp_path):
    """A persisted `Infinity` absorbed every loss, so the breaker never
    tripped: a $1000 loss against a $5 limit did not halt trading. Corrupt
    state must start the day clean instead."""
    import json as _json
    from datetime import datetime, timezone

    from risk.circuit_breaker import DailyCircuitBreaker
    from risk.state import RiskStateStore

    today = datetime.now(timezone.utc).date().isoformat()
    (tmp_path / "daily-risk-state.json").write_text(
        _json.dumps(
            {
                "trading_day": today,
                "realized_pnl_usd": "Infinity",
                "trade_count": 0,
                "halted": False,
                "halt_reason": None,
            }
        )
    )
    breaker = DailyCircuitBreaker(Decimal("5"), RiskStateStore(tmp_path))
    state = breaker.record_realized_pnl(Decimal("-1000"))
    assert state.realized_pnl_usd == Decimal("-1000")
    assert state.halted


def test_nan_persisted_pnl_does_not_crash_the_breach_check(tmp_path):
    """Decimal('NaN') raised InvalidOperation out of `_breached`."""
    import json as _json
    from datetime import datetime, timezone

    from risk.circuit_breaker import DailyCircuitBreaker
    from risk.state import RiskStateStore

    today = datetime.now(timezone.utc).date().isoformat()
    (tmp_path / "daily-risk-state.json").write_text(
        _json.dumps(
            {
                "trading_day": today,
                "realized_pnl_usd": "NaN",
                "trade_count": 0,
                "halted": False,
                "halt_reason": None,
            }
        )
    )
    breaker = DailyCircuitBreaker(Decimal("5"), RiskStateStore(tmp_path))
    # Now also fails closed: a NaN P&L is unreadable state, not a clean day.
    assert not breaker.check().approved
