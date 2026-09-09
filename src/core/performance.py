"""Trade records and performance metrics.

Shared deliberately between backtest and paper mode. The validation gate
compares a 30-day paper run against a backtest, and that comparison is
only meaningful if both numbers were computed by the same code. Two
implementations of "expectancy" would eventually disagree, and the
disagreement would surface as a strategy that passed the gate on
arithmetic rather than on performance.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Sequence

HUNDRED = Decimal(100)


@dataclass(frozen=True)
class ClosedTrade:
    token_mint: str
    entry_at: datetime
    exit_at: datetime
    entry_price: Decimal
    exit_price: Decimal
    size_usd: Decimal
    fees_usd: Decimal
    exit_reason: str

    @property
    def gross_pnl_usd(self) -> Decimal:
        return self.size_usd * (self.exit_price - self.entry_price) / self.entry_price

    @property
    def net_pnl_usd(self) -> Decimal:
        return self.gross_pnl_usd - self.fees_usd

    @property
    def is_win(self) -> bool:
        """A win is net of costs. A gross gain that loses to fees is not a win."""
        return self.net_pnl_usd > 0

    def to_dict(self) -> dict[str, str]:
        return {
            "token_mint": self.token_mint,
            "entry_at": self.entry_at.isoformat(),
            "exit_at": self.exit_at.isoformat(),
            "entry_price": str(self.entry_price),
            "exit_price": str(self.exit_price),
            "size_usd": str(self.size_usd),
            "fees_usd": str(self.fees_usd),
            "exit_reason": self.exit_reason,
        }

    @staticmethod
    def from_dict(raw: dict[str, str]) -> ClosedTrade:
        return ClosedTrade(
            token_mint=raw["token_mint"],
            entry_at=datetime.fromisoformat(raw["entry_at"]),
            exit_at=datetime.fromisoformat(raw["exit_at"]),
            entry_price=Decimal(raw["entry_price"]),
            exit_price=Decimal(raw["exit_price"]),
            size_usd=Decimal(raw["size_usd"]),
            fees_usd=Decimal(raw["fees_usd"]),
            exit_reason=raw["exit_reason"],
        )


def gross_pnl(trades: Sequence[ClosedTrade]) -> Decimal:
    return sum((t.gross_pnl_usd for t in trades), Decimal(0))


def total_fees(trades: Sequence[ClosedTrade]) -> Decimal:
    return sum((t.fees_usd for t in trades), Decimal(0))


def net_pnl(trades: Sequence[ClosedTrade]) -> Decimal:
    return gross_pnl(trades) - total_fees(trades)


def expectancy(trades: Sequence[ClosedTrade]) -> Decimal:
    """Average net P&L per trade — the number the validation gate reads."""
    if not trades:
        return Decimal(0)
    return net_pnl(trades) / Decimal(len(trades))


def win_rate_pct(trades: Sequence[ClosedTrade]) -> Decimal:
    if not trades:
        return Decimal(0)
    wins = sum(1 for t in trades if t.is_win)
    return Decimal(wins) / Decimal(len(trades)) * HUNDRED


def max_drawdown_pct(equity_curve: Sequence[Decimal]) -> Decimal:
    """Largest peak-to-trough decline, in percent of the running peak."""
    if not equity_curve:
        return Decimal(0)
    peak = equity_curve[0]
    worst = Decimal(0)
    for equity in equity_curve:
        peak = max(peak, equity)
        if peak > 0:
            worst = max(worst, (peak - equity) / peak * HUNDRED)
    return worst


def equity_curve_from(
    initial_capital_usd: Decimal, trades: Sequence[ClosedTrade]
) -> list[Decimal]:
    """Equity after each closed trade, starting from initial capital."""
    curve = [initial_capital_usd]
    equity = initial_capital_usd
    for trade in trades:
        equity += trade.net_pnl_usd
        curve.append(equity)
    return curve
