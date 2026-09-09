"""Daily loss circuit breaker.

Once the day's realized loss reaches the configured limit, trading halts
for the rest of that UTC day. The halt latches — it does not lift if a
later mark-to-market looks better, and it is not cleared by restarting the
process. Only a new trading day clears it.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from core.types import RejectionCode, RiskDecision
from risk.state import DailyRiskState, RiskStateStore


class DailyCircuitBreaker:
    def __init__(self, daily_loss_limit_usd: Decimal, store: RiskStateStore) -> None:
        if daily_loss_limit_usd <= 0:
            raise ValueError("daily_loss_limit_usd must be positive")
        self._limit = daily_loss_limit_usd
        self._store = store

    @property
    def limit_usd(self) -> Decimal:
        return self._limit

    def state(self, now: datetime | None = None) -> DailyRiskState:
        return self._store.load(now)

    def check(self, now: datetime | None = None) -> RiskDecision:
        """Veto further trading if the breaker has tripped."""
        state = self._store.load(now)
        if state.halted:
            return RiskDecision.reject(
                RejectionCode.CIRCUIT_BREAKER_TRIPPED,
                f"trading halted for {state.trading_day.isoformat()}: {state.halt_reason}",
            )
        if self._breached(state):
            # Persist the trip even though the breach is only being noticed
            # now — otherwise a restart before the next fill would lose it.
            tripped = self._trip(state)
            return RiskDecision.reject(
                RejectionCode.DAILY_LOSS_LIMIT,
                f"daily loss {-tripped.realized_pnl_usd} USD reached limit {self._limit} USD",
            )
        return RiskDecision.approve()

    def record_realized_pnl(
        self, pnl_usd: Decimal, now: datetime | None = None
    ) -> DailyRiskState:
        """Record a closed trade's P&L, tripping the breaker if it breaches."""
        state = self._store.load(now).with_pnl(pnl_usd)
        if self._breached(state):
            state = self._trip(state)
        else:
            self._store.save(state)
        return state

    def remaining_loss_budget_usd(self, now: datetime | None = None) -> Decimal:
        state = self._store.load(now)
        return max(Decimal("0"), self._limit + min(Decimal("0"), state.realized_pnl_usd))

    def _breached(self, state: DailyRiskState) -> bool:
        # realized_pnl is negative for a loss; the limit is expressed positive.
        return -state.realized_pnl_usd >= self._limit

    def _trip(self, state: DailyRiskState) -> DailyRiskState:
        halted = state.halt(
            f"daily loss limit breached: {-state.realized_pnl_usd} USD "
            f"against a {self._limit} USD limit"
        )
        self._store.save(halted)
        return halted
