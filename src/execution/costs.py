"""Fixed-cost modelling.

At $5–$10 position sizes, fixed costs dominate the outcome. They do not
scale down with the trade, so a small trade bears a disproportionate share
of them — this is the single biggest reason a strategy that looks
profitable gross is unprofitable net.

Modelling them pessimistically here is what makes the paper run's
expectancy number mean something.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from core.config import CostsConfig

LAMPORTS_PER_SOL = Decimal("1000000000")
MICROLAMPORTS_PER_LAMPORT = Decimal("1000000")


@dataclass(frozen=True)
class TradeCosts:
    network_fee_usd: Decimal
    priority_fee_usd: Decimal
    account_rent_usd: Decimal
    platform_fee_usd: Decimal

    @property
    def total_usd(self) -> Decimal:
        return (
            self.network_fee_usd
            + self.priority_fee_usd
            + self.account_rent_usd
            + self.platform_fee_usd
        )

    def as_pct_of(self, size_usd: Decimal) -> Decimal:
        if size_usd <= 0:
            raise ValueError("size_usd must be positive")
        return (self.total_usd / size_usd) * Decimal(100)


class CostModel:
    def __init__(self, config: CostsConfig) -> None:
        self._config = config

    def _lamports_to_usd(self, lamports: Decimal) -> Decimal:
        return (lamports / LAMPORTS_PER_SOL) * self._config.sol_price_usd

    def estimate(self, size_usd: Decimal, creates_token_account: bool = False) -> TradeCosts:
        """Estimate the all-in cost of one swap.

        `creates_token_account` matters more than it looks: the associated
        token account rent is charged the first time this wallet touches a
        given mint, and at these sizes it can exceed every other fee
        combined.
        """
        if size_usd <= 0:
            raise ValueError("size_usd must be positive")

        priority_lamports = (
            Decimal(self._config.priority_fee_microlamports) / MICROLAMPORTS_PER_LAMPORT
        )
        return TradeCosts(
            network_fee_usd=self._lamports_to_usd(Decimal(self._config.base_fee_lamports)),
            priority_fee_usd=self._lamports_to_usd(priority_lamports),
            account_rent_usd=(
                self._lamports_to_usd(Decimal(self._config.ata_rent_lamports))
                if creates_token_account
                else Decimal("0")
            ),
            platform_fee_usd=size_usd
            * Decimal(self._config.platform_fee_bps)
            / Decimal(10000),
        )
