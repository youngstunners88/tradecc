"""Authorisation to send exactly one transaction.

CLAUDE.md rule 3 says every swap simulates before it sends. Stated as prose
that is an intention; the enforcement problem is that "simulate, then send" in
sequence still permits sending *something else* — a rebuilt transaction, a
stale one, a retry with a refreshed blockhash that was never itself simulated.

So authorisation is bound to bytes. `authorize_send` returns a
`SendAuthorization` carrying the digest of the exact transaction that was
simulated. The sender (Stage 6b, not yet written) will require one and compare
digests. A transaction that differs by a single byte from the simulated one has
no authorisation and cannot be sent — not by policy, but because the token it
would need does not exist.

Every precondition is checked here, in one place, and every failure is a
refusal rather than an exception. The checks compose the existing engine rather
than reimplementing it: `RiskEngine.approve` already owns position sizing, the
slippage cap, the circuit breaker and the live gate, and a second
implementation of any of them would eventually disagree with the first.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from core.types import (
    Mode,
    RejectionCode,
    RiskDecision,
    SimulationOutcome,
    TradeIntent,
    digest_of,
)

# How stale a simulation may be before it is worthless. Solana blockhashes
# expire after ~150 slots (~60s); a simulation older than that describes chain
# state the transaction will never meet.
MAX_SIMULATION_AGE = timedelta(seconds=30)


@dataclass(frozen=True)
class SendAuthorization:
    """Permission to send one specific transaction, once.

    Deliberately holds no method that sends anything. It is evidence, not
    capability — the sender takes one of these and the bytes, and refuses if
    they disagree.
    """

    transaction_digest: str
    authorized_at: datetime
    size_usd: str

    def authorizes(self, transaction_bytes: bytes) -> bool:
        return digest_of(transaction_bytes) == self.transaction_digest


@dataclass(frozen=True)
class PreflightResult:
    """Either an authorisation or the reasons there is none. Never both."""

    authorization: SendAuthorization | None
    refusals: tuple[tuple[RejectionCode, str], ...] = ()

    @property
    def authorized(self) -> bool:
        return self.authorization is not None

    def describe(self) -> str:
        if self.authorized:
            return "send authorized"
        return "send REFUSED — " + "; ".join(detail for _, detail in self.refusals)

    @property
    def codes(self) -> tuple[RejectionCode, ...]:
        return tuple(code for code, _ in self.refusals)


def authorize_send(
    *,
    intent: TradeIntent,
    risk_decision: RiskDecision,
    simulation: SimulationOutcome | None,
    transaction_bytes: bytes,
    configured_mode: Mode,
    now: datetime,
) -> PreflightResult:
    """Every precondition for sending, evaluated together.

    Keyword-only on purpose: these arguments are not interchangeable, and a
    positional mix-up here sends the wrong transaction.
    """
    refusals: list[tuple[RejectionCode, str]] = []

    # Risk first. It owns sizing, slippage, the breaker and the live gate, and
    # its verdict is not re-derived here.
    if not risk_decision.approved:
        refusals.extend(risk_decision.rejections)

    # A live send from a process not configured for live is a configuration
    # error, and configuration errors around real money fail closed.
    if configured_mode is not Mode.LIVE:
        refusals.append((
            RejectionCode.LIVE_GATE_NOT_MET,
            f"configured mode is {configured_mode.value!r}, not 'live' — refusing to send",
        ))
    if intent.mode is not Mode.LIVE:
        refusals.append((
            RejectionCode.LIVE_GATE_NOT_MET,
            f"intent mode is {intent.mode.value!r}, not 'live' — refusing to send",
        ))

    refusals.extend(_check_simulation(simulation, transaction_bytes, now))

    if refusals:
        return PreflightResult(authorization=None, refusals=tuple(refusals))
    return PreflightResult(
        authorization=SendAuthorization(
            transaction_digest=digest_of(transaction_bytes),
            authorized_at=now,
            size_usd=str(intent.size_usd),
        )
    )


def _check_simulation(
    simulation: SimulationOutcome | None, transaction_bytes: bytes, now: datetime
) -> list[tuple[RejectionCode, str]]:
    """No simulation, a failed one, a stale one, or one of different bytes."""
    if simulation is None:
        return [(
            RejectionCode.LIVE_GATE_NOT_MET,
            "no simulation performed — CLAUDE.md rule 3 requires every swap to "
            "simulate before it sends",
        )]
    if not simulation.succeeded:
        return [(
            RejectionCode.LIVE_GATE_NOT_MET,
            f"simulation failed ({simulation.error or 'no error reported'})",
        )]
    if simulation.transaction_digest != digest_of(transaction_bytes):
        return [(
            RejectionCode.LIVE_GATE_NOT_MET,
            "simulation was of a different transaction than the one being sent — "
            "rebuild and re-simulate rather than reusing the result",
        )]
    age = now - simulation.simulated_at
    if age < timedelta(0):
        return [(
            RejectionCode.LIVE_GATE_NOT_MET,
            "simulation is timestamped in the future — refusing to reason about it",
        )]
    if age > MAX_SIMULATION_AGE:
        return [(
            RejectionCode.LIVE_GATE_NOT_MET,
            f"simulation is {age.total_seconds():.0f}s old, limit is "
            f"{MAX_SIMULATION_AGE.total_seconds():.0f}s — chain state has moved",
        )]
    return []
