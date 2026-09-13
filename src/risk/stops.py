"""Per-trade stop-loss and take-profit evaluation.

This is a pure function over a position and a current price. It decides
*that* a position should close, not how — closing is execution's job, and
keeping the decision network-free is what makes it testable.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from core.config import RiskConfig
from core.types import Position


class StopAction(str, Enum):
    HOLD = "hold"
    STOP_LOSS = "stop_loss"
    TAKE_PROFIT = "take_profit"


@dataclass(frozen=True)
class StopEvaluation:
    action: StopAction
    pnl_pct: Decimal
    pnl_usd: Decimal
    reason: str

    @property
    def should_close(self) -> bool:
        return self.action is not StopAction.HOLD


HUNDRED = Decimal(100)


def stop_loss_price(position: Position, config: RiskConfig) -> Decimal:
    """The price at which this position's stop-loss triggers.

    Exposed so a bar-based simulation can ask "did the market touch this
    level?" against the bar's low, rather than only against its close.
    Checking the close alone silently ignores stops that were hit intrabar
    and recovered, which flatters the strategy.
    """
    return position.entry_price * (
        Decimal(1) - config.per_trade_stop_loss_pct / HUNDRED
    )


def take_profit_price(position: Position, config: RiskConfig) -> Decimal:
    return position.entry_price * (
        Decimal(1) + config.per_trade_take_profit_pct / HUNDRED
    )


def evaluate_stops(
    position: Position, current_price: Decimal, config: RiskConfig
) -> StopEvaluation:
    if current_price <= 0:
        raise ValueError("current_price must be positive")

    pnl_pct = position.unrealized_pnl_pct(current_price)
    pnl_usd = position.unrealized_pnl_usd(current_price)

    # Stop-loss is checked first: if a single bar spans both thresholds we
    # assume the adverse one, rather than booking a profit we may not have got.
    if pnl_pct <= -config.per_trade_stop_loss_pct:
        return StopEvaluation(
            StopAction.STOP_LOSS,
            pnl_pct,
            pnl_usd,
            f"loss {pnl_pct:.4f}% reached stop-loss -{config.per_trade_stop_loss_pct}%",
        )
    if pnl_pct >= config.per_trade_take_profit_pct:
        return StopEvaluation(
            StopAction.TAKE_PROFIT,
            pnl_pct,
            pnl_usd,
            f"gain {pnl_pct:.4f}% reached take-profit {config.per_trade_take_profit_pct}%",
        )
    return StopEvaluation(StopAction.HOLD, pnl_pct, pnl_usd, "within stop bounds")
