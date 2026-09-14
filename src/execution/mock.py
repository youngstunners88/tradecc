"""A deterministic quote source for tests and offline runs.

This is the seam that lets strategy and risk be exercised end-to-end with
no network at all. It is not a substitute for testing the real clients —
those are tested against a fake HTTP transport, so their retry and
rate-limit logic is covered too.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from core.types import Quote, Side


@dataclass
class QuoteCall:
    input_mint: str
    output_mint: str
    amount_atomic: int
    slippage_bps: int
    amount_usd: Decimal
    side: Side


class MockQuoteSource:
    """Returns a quote with a configurable, exact slippage.

    `slippage_pct` is what the returned quote will report, so a test can
    ask for precisely the number it wants to assert against rather than
    reverse-engineering prices.

    **It models the side.** It used to return `expected * (1 + slippage)` as
    the worst case regardless of direction, which is adverse only for a BUY —
    on a SELL it handed back a *better* price than expected. Every paper test
    therefore ran against a quote source that could not express the SELL-side
    unit error that existed in the real Jupiter client, which is why the suite
    was green while a flat market produced +$990 on a $10 position.
    """

    def __init__(
        self,
        expected_price: Decimal = Decimal("100"),
        slippage_pct: Decimal = Decimal("0.2"),
        fee_usd: Decimal = Decimal("0"),
    ) -> None:
        self.expected_price = expected_price
        self.slippage_pct = slippage_pct
        self.fee_usd = fee_usd
        self.calls: list[QuoteCall] = []

    def get_quote(
        self,
        input_mint: str,
        output_mint: str,
        amount_atomic: int,
        slippage_bps: int,
        amount_usd: Decimal,
        input_decimals: int = 6,
        output_decimals: int = 9,
        *,
        side: Side = Side.BUY,
    ) -> Quote:
        self.calls.append(
            QuoteCall(input_mint, output_mint, amount_atomic, slippage_bps, amount_usd, side)
        )
        drift = self.slippage_pct / Decimal(100)
        # Adverse means "worse for us", which is a higher price when buying
        # and a lower one when selling.
        if side is Side.BUY:
            worst_case = self.expected_price * (Decimal(1) + drift)
        else:
            worst_case = self.expected_price * (Decimal(1) - drift)
        return Quote(
            token_mint=output_mint if side is Side.BUY else input_mint,
            side=side,
            amount_usd=amount_usd,
            expected_price=self.expected_price,
            worst_case_price=worst_case,
            fee_usd=self.fee_usd,
            source="mock",
        )
