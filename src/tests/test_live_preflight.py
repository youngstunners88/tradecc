"""Nothing may be sent without an authorisation bound to its exact bytes.

Every test here forces one precondition to fail and asserts the result is a
refusal. The suite is the argument that the refusals are real: a guard nobody
has watched fail is a guard nobody has tested.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from core.types import (
    Mode,
    Quote,
    RejectionCode,
    RiskDecision,
    Side,
    Signal,
    SignalType,
    TradeIntent,
)
from live.preflight import (
    MAX_SIMULATION_AGE,
    PreflightResult,
    SimulationOutcome,
    authorize_send,
    digest_of,
)

NOW = datetime(2026, 9, 13, 12, 0, tzinfo=timezone.utc)
TOKEN = "So11111111111111111111111111111111111111112"
TX = b"serialized-transaction-bytes"


def make_intent(mode: Mode = Mode.LIVE) -> TradeIntent:
    return TradeIntent(
        signal=Signal(
            type=SignalType.BUY,
            token_mint=TOKEN,
            price=Decimal("100"),
            timestamp=NOW,
            strategy="test",
        ),
        quote=Quote(
            token_mint=TOKEN,
            side=Side.BUY,
            amount_usd=Decimal("10"),
            expected_price=Decimal("100"),
            worst_case_price=Decimal("100.2"),
            fee_usd=Decimal("0.02"),
            source="test",
        ),
        size_usd=Decimal("10"),
        mode=mode,
    )


def good_simulation(tx: bytes = TX, at: datetime = NOW) -> SimulationOutcome:
    return SimulationOutcome(transaction_digest=digest_of(tx), succeeded=True, simulated_at=at)


def preflight(**overrides) -> PreflightResult:
    kwargs = {
        "intent": make_intent(),
        "risk_decision": RiskDecision.approve(),
        "simulation": good_simulation(),
        "transaction_bytes": TX,
        "configured_mode": Mode.LIVE,
        "now": NOW,
    }
    kwargs.update(overrides)
    return authorize_send(**kwargs)


def test_all_preconditions_met_authorizes_those_exact_bytes():
    result = preflight()

    assert result.authorized
    assert result.authorization.authorizes(TX)
    assert result.authorization.size_usd == "10"


def test_authorization_does_not_cover_any_other_bytes():
    """The whole point: authorisation is for bytes, not for an occasion."""
    result = preflight()

    assert not result.authorization.authorizes(TX + b"!")
    assert not result.authorization.authorizes(b"")


def test_a_risk_rejection_refuses_and_is_not_re_derived():
    """Risk owns sizing, slippage, the breaker and the gate. Preflight carries
    its verdict through rather than forming a second opinion."""
    rejected = RiskDecision.reject(RejectionCode.DAILY_LOSS_LIMIT, "daily loss limit reached")

    result = preflight(risk_decision=rejected)

    assert not result.authorized
    assert RejectionCode.DAILY_LOSS_LIMIT in result.codes
    assert "daily loss limit reached" in result.describe()


def test_no_simulation_refuses():
    """CLAUDE.md rule 3. The default must be refusal, not a warning."""
    result = preflight(simulation=None)

    assert not result.authorized
    assert "no simulation performed" in result.describe()


def test_failed_simulation_refuses():
    result = preflight(
        simulation=SimulationOutcome(
            transaction_digest=digest_of(TX),
            succeeded=False,
            simulated_at=NOW,
            error="InsufficientFundsForRent",
        )
    )

    assert not result.authorized
    assert "InsufficientFundsForRent" in result.describe()


def test_simulation_of_different_bytes_refuses():
    """The failure mode prose cannot prevent: simulate one transaction, send
    another. A rebuilt or blockhash-refreshed transaction is a different one."""
    result = preflight(simulation=good_simulation(tx=b"a-different-transaction"))

    assert not result.authorized
    assert "different transaction" in result.describe()


def test_stale_simulation_refuses():
    """A simulation older than blockhash lifetime describes state the
    transaction will never meet."""
    stale = NOW - MAX_SIMULATION_AGE - timedelta(seconds=1)

    result = preflight(simulation=good_simulation(at=stale))

    assert not result.authorized
    assert "old" in result.describe()


def test_simulation_at_the_age_limit_is_still_good():
    result = preflight(simulation=good_simulation(at=NOW - MAX_SIMULATION_AGE))

    assert result.authorized


def test_simulation_from_the_future_refuses():
    """A clock disagreement is not a reason to trust a result."""
    result = preflight(simulation=good_simulation(at=NOW + timedelta(seconds=5)))

    assert not result.authorized
    assert "future" in result.describe()


@pytest.mark.parametrize("mode", [Mode.PAPER, Mode.BACKTEST])
def test_a_process_not_configured_for_live_cannot_send(mode):
    result = preflight(configured_mode=mode)

    assert not result.authorized
    assert RejectionCode.LIVE_GATE_NOT_MET in result.codes


@pytest.mark.parametrize("mode", [Mode.PAPER, Mode.BACKTEST])
def test_an_intent_not_claiming_live_cannot_send(mode):
    result = preflight(intent=make_intent(mode=mode))

    assert not result.authorized
    assert RejectionCode.LIVE_GATE_NOT_MET in result.codes


def test_every_failure_is_reported_not_just_the_first():
    """Fixing one refusal must not reveal the next one at send time."""
    result = preflight(
        risk_decision=RiskDecision.reject(RejectionCode.SLIPPAGE_EXCEEDED, "slippage"),
        configured_mode=Mode.PAPER,
        simulation=None,
    )

    assert not result.authorized
    assert len(result.refusals) >= 3


def test_a_refusal_carries_no_authorization_at_all():
    """Not a falsy one, not an expired one — none. There is nothing to misuse."""
    result = preflight(simulation=None)

    assert result.authorization is None
    assert not result.authorized


def test_preflight_exposes_no_way_to_send():
    """Evidence, not capability. If this type ever grows a send method, the
    refusal-first design has been inverted."""
    result = preflight()
    surface = {name for name in dir(result.authorization) if not name.startswith("_")}

    assert surface == {"transaction_digest", "authorized_at", "size_usd", "authorizes"}
