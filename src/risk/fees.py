"""Refuse a trade whose modelled cost is absurd relative to its size.

Fees are quoted in lamports and converted to USD at a SOL price read from the
market. That conversion is the weak link: nothing downstream sanity-checks the
result, so a corrupted or misattributed price inflates the estimate without
bound. A stress run at a corrupted SOL price produced a modelled cost of
**38,880% of a $10 position**, and every other control approved the trade —
position size was $10, slippage was in band, the breaker was clean, so nothing
had grounds to object.

The check deliberately compares fees to *size* rather than validating the SOL
price against a plausible band. A band is a market assumption that goes stale;
this repo already shipped a hardcoded `sol_price_usd: 200` that was wrong by
2x within days. "Costs should not dwarf the trade" needs no such assumption.

It abstains when the caller did not estimate a cost. An unmeasured fee is not
a small one, and silently reading `None` as zero would turn the one path that
cannot see costs into the one path that never gets checked.
"""

from __future__ import annotations

from decimal import Decimal

from core.config import RiskConfig
from core.types import RejectionCode, RiskDecision


def check_fee_ratio(
    estimated_fee_usd: Decimal | None, size_usd: Decimal, config: RiskConfig
) -> RiskDecision:
    if estimated_fee_usd is None:
        return RiskDecision.approve()
    if size_usd <= 0:
        # Position sizing owns this rejection; duplicating it here would give
        # one bad input two different reasons in the log.
        return RiskDecision.approve()

    cap = size_usd * config.max_fee_fraction_of_size
    if estimated_fee_usd > cap:
        pct = estimated_fee_usd / size_usd * Decimal(100)
        return RiskDecision.reject(
            RejectionCode.FEES_EXCEED_SIZE,
            f"modelled cost {estimated_fee_usd} USD is {pct:.1f}% of a "
            f"{size_usd} USD trade, above the {config.max_fee_fraction_of_size} "
            "ceiling — check the SOL price feed before trading",
        )
    return RiskDecision.approve()
