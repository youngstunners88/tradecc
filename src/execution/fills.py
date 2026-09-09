"""Simulated fills for backtest and paper modes.

Fills are simulated at the quote's **worst-case** price, not its expected
price. That is a deliberate pessimism: a paper run that assumes best-case
fills will clear the validation gate and then underperform live, and the
whole point of the gate is to catch that before real money is involved.
The bias is always toward the outcome that makes the strategy look worse.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from core.types import Fill, Quote, utc_now
from execution.costs import CostModel, TradeCosts


class FillSimulator:
    def __init__(self, cost_model: CostModel) -> None:
        self._cost_model = cost_model

    def simulate(
        self,
        quote: Quote,
        size_usd: Decimal,
        at: datetime | None = None,
        creates_token_account: bool = False,
    ) -> Fill:
        costs = self.estimate_costs(size_usd, creates_token_account)
        return Fill(
            token_mint=quote.token_mint,
            side=quote.side,
            price=quote.worst_case_price,
            size_usd=size_usd,
            fee_usd=costs.total_usd,
            timestamp=at or utc_now(),
            simulated=True,
            tx_signature=None,
        )

    def estimate_costs(
        self, size_usd: Decimal, creates_token_account: bool = False
    ) -> TradeCosts:
        return self._cost_model.estimate(size_usd, creates_token_account)
