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

# Wrapped SOL.
WRAPPED_SOL_MINT = "So11111111111111111111111111111111111111112"


def sol_price_from_close(token_mint: str, close: Decimal) -> Decimal | None:
    """The SOL price implied by a bar, when the bar is a SOL/USD bar.

    Trading SOL against a USD-quoted pool means the close *is* the SOL
    price, so SOL-denominated costs can be priced exactly and offline
    rather than against a config constant that drifts. Returns `None` for
    any other mint, so callers fall back to config instead of pricing an
    unrelated token's close as if it were SOL.

    Shared by backtest and paper deliberately: two implementations would
    eventually disagree, and the disagreement would show up as a strategy
    clearing the gate on arithmetic rather than performance.
    """
    if token_mint == WRAPPED_SOL_MINT:
        return close
    return None


@dataclass(frozen=True)
class TradeCosts:
    network_fee_usd: Decimal
    priority_fee_usd: Decimal
    jito_tip_usd: Decimal
    account_rent_usd: Decimal
    platform_fee_usd: Decimal
    sol_price_usd: Decimal

    @property
    def total_usd(self) -> Decimal:
        return (
            self.network_fee_usd
            + self.priority_fee_usd
            + self.jito_tip_usd
            + self.account_rent_usd
            + self.platform_fee_usd
        )

    @property
    def recurring_usd(self) -> Decimal:
        """Cost paid on every transaction.

        Excludes account rent, which is charged once per mint and is a
        refundable rent-exempt deposit rather than a fee. Conflating the
        two made a one-time deposit look like a per-trade cost and badly
        distorted the earlier cost analysis.
        """
        return self.total_usd - self.account_rent_usd

    def as_pct_of(self, size_usd: Decimal) -> Decimal:
        if size_usd <= 0:
            raise ValueError("size_usd must be positive")
        return (self.total_usd / size_usd) * Decimal(100)


class CostModel:
    def __init__(self, config: CostsConfig) -> None:
        self._config = config

    def _lamports_to_usd(self, lamports: Decimal, sol_price_usd: Decimal) -> Decimal:
        return (lamports / LAMPORTS_PER_SOL) * sol_price_usd

    def priority_fee_lamports(self) -> Decimal:
        """Compute-unit limit times price per unit.

        Priority fees are quoted per compute unit. Treating the
        microlamport figure as a flat total understated this by the size
        of the CU limit — a swap at 200k CU costs ~40,000 lamports, not
        the 0.2 lamports the flat reading produced.
        """
        return (
            Decimal(self._config.compute_unit_limit)
            * Decimal(self._config.priority_fee_microlamports_per_cu)
            / MICROLAMPORTS_PER_LAMPORT
        )

    def estimate(
        self,
        size_usd: Decimal,
        creates_token_account: bool = False,
        sol_price_usd: Decimal | None = None,
    ) -> TradeCosts:
        """Estimate the all-in cost of one swap.

        `creates_token_account` matters more than it looks: the associated
        token account rent is charged the first time this wallet touches a
        given mint, and at these sizes it can exceed every other fee
        combined.

        `sol_price_usd` overrides the config fallback. Pass a live price
        in paper/live, or the bar's own close when backtesting a
        SOL-quoted pair — every SOL-denominated cost scales with it, so a
        stale constant misprices all of them at once.
        """
        if size_usd <= 0:
            raise ValueError("size_usd must be positive")

        price = self._config.sol_price_usd if sol_price_usd is None else sol_price_usd
        if price <= 0:
            raise ValueError("sol_price_usd must be positive")

        return TradeCosts(
            network_fee_usd=self._lamports_to_usd(
                Decimal(self._config.base_fee_lamports), price
            ),
            priority_fee_usd=self._lamports_to_usd(self.priority_fee_lamports(), price),
            jito_tip_usd=self._lamports_to_usd(
                Decimal(self._config.jito_tip_lamports), price
            ),
            account_rent_usd=(
                self._lamports_to_usd(Decimal(self._config.ata_rent_lamports), price)
                if creates_token_account
                else Decimal("0")
            ),
            platform_fee_usd=size_usd
            * Decimal(self._config.platform_fee_bps)
            / Decimal(10000),
            sol_price_usd=price,
        )
