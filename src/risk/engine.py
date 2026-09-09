"""The risk engine — the single veto point for every trade.

`execution/` must call `approve()` before acting on any intent, in every
mode including backtest and paper. Running the same checks in simulated
modes is what makes the paper run evidence about the live system rather
than evidence about a different, more permissive one.

The engine is strategy-agnostic on purpose: it consumes a `TradeIntent`
and knows nothing about how the signal was produced, so v0.2 copy-trading
plugs in without touching this file.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from core.config import RunConfig
from core.gate import GateResult, evaluate_live_gate
from core.logging import get_logger
from core.types import Mode, Position, RejectionCode, RiskDecision, TradeIntent
from risk.circuit_breaker import DailyCircuitBreaker
from risk.position_sizing import check_position_size
from risk.slippage import check_slippage
from risk.state import DailyRiskState, RiskStateStore
from risk.stops import StopEvaluation, evaluate_stops

logger = get_logger("tradecc.risk")


class RiskEngine:
    def __init__(self, config: RunConfig, store: RiskStateStore | None = None) -> None:
        self._config = config
        self._store = store or RiskStateStore(config.state_dir)
        self._breaker = DailyCircuitBreaker(config.risk.daily_loss_limit_usd, self._store)

    @property
    def circuit_breaker(self) -> DailyCircuitBreaker:
        return self._breaker

    def live_gate(self) -> GateResult:
        return evaluate_live_gate(self._config.gate_file)

    def approve(self, intent: TradeIntent, now: datetime | None = None) -> RiskDecision:
        """Run every risk check against a proposed trade.

        All checks run even after one fails, so the log shows every reason a
        trade was rejected rather than only the first.
        """
        decision = RiskDecision.approve()
        decision = decision.merged_with(self._check_live_gate(intent))
        decision = decision.merged_with(self._breaker.check(now))
        decision = decision.merged_with(check_position_size(intent.size_usd, self._config.risk))
        decision = decision.merged_with(
            check_slippage(intent.quote, self._config.risk.max_slippage_pct)
        )

        logger.info(
            "risk_decision",
            extra={
                "approved": decision.approved,
                "mode": intent.mode.value,
                "token_mint": intent.signal.token_mint,
                "side": intent.quote.side.value,
                "size_usd": intent.size_usd,
                "slippage_pct": intent.quote.slippage_pct,
                "rejections": [code.value for code in decision.codes],
                "detail": decision.describe(),
            },
        )
        return decision

    def evaluate_position(
        self, position: Position, current_price: Decimal
    ) -> StopEvaluation:
        """Check a held position against its stop-loss / take-profit bounds."""
        evaluation = evaluate_stops(position, current_price, self._config.risk)
        if evaluation.should_close:
            logger.info(
                "stop_triggered",
                extra={
                    "action": evaluation.action.value,
                    "token_mint": position.token_mint,
                    "pnl_pct": evaluation.pnl_pct,
                    "pnl_usd": evaluation.pnl_usd,
                    "reason": evaluation.reason,
                },
            )
        return evaluation

    def record_realized_pnl(
        self, pnl_usd: Decimal, now: datetime | None = None
    ) -> DailyRiskState:
        """Book a closed trade's P&L and trip the breaker if it breaches."""
        state = self._breaker.record_realized_pnl(pnl_usd, now)
        if state.halted:
            logger.warning(
                "circuit_breaker_tripped",
                extra={
                    "trading_day": state.trading_day.isoformat(),
                    "realized_pnl_usd": state.realized_pnl_usd,
                    "limit_usd": self._config.risk.daily_loss_limit_usd,
                    "reason": state.halt_reason,
                },
            )
        return state

    def _check_live_gate(self, intent: TradeIntent) -> RiskDecision:
        if intent.mode is not Mode.LIVE:
            return RiskDecision.approve()
        result = self.live_gate()
        if result.unlocked:
            return RiskDecision.approve()
        return RiskDecision.reject(RejectionCode.LIVE_GATE_NOT_MET, result.describe())
