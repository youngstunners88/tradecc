"""Slippage cap enforcement.

Slippage is measured against the quote's *worst-case* leg, not its
expected price. At $5–$10 sizes, fixed costs and slippage dominate the
outcome, so a check that only reads the optimistic number would approve
trades that cannot be profitable.
"""

from __future__ import annotations

from decimal import Decimal

from core.types import Quote, RejectionCode, RiskDecision


def check_slippage(quote: Quote, max_slippage_pct: Decimal) -> RiskDecision:
    if max_slippage_pct <= 0:
        raise ValueError("max_slippage_pct must be positive")

    effective = quote.slippage_pct
    if effective > max_slippage_pct:
        return RiskDecision.reject(
            RejectionCode.SLIPPAGE_EXCEEDED,
            f"effective slippage {effective:.4f}% exceeds cap {max_slippage_pct}% "
            f"(expected {quote.expected_price}, worst case {quote.worst_case_price})",
        )
    return RiskDecision.approve()
