"""Position sizing and its ceiling.

`RiskConfig` already refuses to load an oversized default, but that only
covers sizes written in a config file. This check covers sizes computed at
runtime, which is where a scaling bug would actually show up.
"""

from __future__ import annotations

from decimal import Decimal

from core.config import POSITION_SIZE_SOFT_CEILING_USD, RiskConfig
from core.types import RejectionCode, RiskDecision


def resolve_position_size(config: RiskConfig) -> Decimal:
    return config.position_size_usd


def check_position_size(size_usd: Decimal, config: RiskConfig) -> RiskDecision:
    if size_usd <= 0:
        return RiskDecision.reject(
            RejectionCode.POSITION_SIZE_INVALID,
            f"position size {size_usd} USD is not positive",
        )
    if size_usd > config.position_size_usd:
        return RiskDecision.reject(
            RejectionCode.POSITION_SIZE_EXCEEDED,
            f"position size {size_usd} USD exceeds configured "
            f"{config.position_size_usd} USD",
        )
    if size_usd > POSITION_SIZE_SOFT_CEILING_USD and not config.position_size_override_ack:
        return RiskDecision.reject(
            RejectionCode.POSITION_SIZE_EXCEEDED,
            f"position size {size_usd} USD exceeds the "
            f"{POSITION_SIZE_SOFT_CEILING_USD} USD ceiling without an explicit override",
        )
    return RiskDecision.approve()
