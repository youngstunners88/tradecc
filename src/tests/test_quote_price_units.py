"""The price convention, pinned end to end against a Jupiter-shaped provider.

This file exists because the unit suite was green while a flat market produced
**+$990 of profit on a $10 position**. Every paper test used a quote source
that returned one price orientation for both sides, so nothing could express
the error the real client actually made: `in/out` is quote-asset-per-token on a
BUY and its reciprocal on a SELL.

These tests cross the seam deliberately — a fake HTTP transport answering like
Jupiter, then the arithmetic that P&L and the stops actually perform.
"""

from __future__ import annotations

import json
from decimal import Decimal
from urllib.parse import parse_qs, urlparse

import pytest

from core.config import ProvidersConfig
from core.performance import ClosedTrade
from core.rate_limit import RateLimiter
from core.types import Side
from execution.http import HttpResponse, RetryPolicy
from execution.jupiter import JupiterQuoteClient

USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
SOL = "So11111111111111111111111111111111111111112"
USDC_DECIMALS, SOL_DECIMALS = 6, 9

SOL_PRICE_USD = 100
SLIPPAGE_BPS_APPLIED = 2  # 0.2%


class FlatMarket:
    """Answers like Jupiter with SOL pinned at $100 on both legs."""

    def __init__(self, price_usd: int = SOL_PRICE_USD) -> None:
        self.price_usd = price_usd

    def request(self, method, url, *, headers=None, body=None, timeout=None):
        query = parse_qs(urlparse(url).query)
        amount = int(query["amount"][0])
        input_mint = query["inputMint"][0]
        if input_mint == USDC:  # BUY: spend USDC, receive SOL
            out = amount * 10**SOL_DECIMALS // (self.price_usd * 10**USDC_DECIMALS)
        else:  # SELL: spend SOL, receive USDC
            out = amount * (self.price_usd * 10**USDC_DECIMALS) // 10**SOL_DECIMALS
        threshold = out * (1000 - SLIPPAGE_BPS_APPLIED) // 1000
        return HttpResponse(
            200,
            json.dumps(
                {
                    "inputMint": input_mint,
                    "inAmount": str(amount),
                    "outputMint": query["outputMint"][0],
                    "outAmount": str(out),
                    "otherAmountThreshold": str(threshold),
                    "swapMode": "ExactIn",
                    "slippageBps": 50,
                }
            ).encode(),
            {},
        )


def client(transport=None) -> JupiterQuoteClient:
    return JupiterQuoteClient(
        ProvidersConfig(),
        transport=transport or FlatMarket(),
        limiter=RateLimiter(1000, 60.0, name="jupiter"),
        retry=RetryPolicy(max_attempts=1),
    )


def buy_quote(c, usd: int = 10):
    return c.get_quote(
        input_mint=USDC,
        output_mint=SOL,
        amount_atomic=usd * 10**USDC_DECIMALS,
        slippage_bps=50,
        amount_usd=Decimal(usd),
        input_decimals=USDC_DECIMALS,
        output_decimals=SOL_DECIMALS,
        side=Side.BUY,
    )


def sell_quote(c, sol: Decimal = Decimal("0.1"), usd: int = 10):
    return c.get_quote(
        input_mint=SOL,
        output_mint=USDC,
        amount_atomic=int(sol * 10**SOL_DECIMALS),
        slippage_bps=50,
        amount_usd=Decimal(usd),
        input_decimals=SOL_DECIMALS,
        output_decimals=USDC_DECIMALS,
        side=Side.SELL,
    )


def test_both_sides_price_in_the_same_units():
    """The regression. Entry from a BUY and exit from a SELL, flat market.

    Before the fix these were 0.1002 and 10.02 — reciprocals — and the P&L
    below came out at +$990.00 on a $10 position that never moved.
    """
    c = client()
    entry = buy_quote(c).worst_case_price
    exit_price = sell_quote(c).worst_case_price

    trade = ClosedTrade(
        token_mint=SOL,
        entry_at=None,
        exit_at=None,
        entry_price=entry,
        exit_price=exit_price,
        size_usd=Decimal(10),
        fees_usd=Decimal(0),
        exit_reason="strategy_sell",
    )

    # Round trip in a flat market: pay 0.2% entering, lose 0.2% leaving.
    assert trade.gross_pnl_usd < 0, "a flat-market round trip cannot be profitable"
    assert trade.gross_pnl_usd > Decimal("-0.05"), (
        f"loss should be about two slippage legs on $10, got {trade.gross_pnl_usd}"
    )


def test_a_quote_price_is_comparable_to_a_candle_close():
    """Stops and take-profits compare these prices against candle closes. An
    atomic ratio (0.1) would make every comparison against a $100 close
    meaningless in a way no exception would reveal."""
    c = client()
    assert buy_quote(c).expected_price == Decimal(SOL_PRICE_USD)
    assert sell_quote(c).expected_price == Decimal(SOL_PRICE_USD)


@pytest.mark.parametrize(
    "side,expect_worse_higher",
    [(Side.BUY, True), (Side.SELL, False)],
)
def test_worst_case_is_adverse_for_the_side(side, expect_worse_higher):
    c = client()
    quote = buy_quote(c) if side is Side.BUY else sell_quote(c)
    if expect_worse_higher:
        assert quote.worst_case_price > quote.expected_price
    else:
        assert quote.worst_case_price < quote.expected_price


def test_a_sell_quote_names_the_token_not_the_quote_asset():
    assert sell_quote(client()).token_mint == SOL


def test_slippage_pct_survives_the_reorientation():
    """slippage_pct feeds the risk engine's cap. It must stay a magnitude in
    percent on both sides, not go negative because the SELL price fell."""
    c = client()
    for quote in (buy_quote(c), sell_quote(c)):
        assert quote.slippage_pct > 0
        assert quote.slippage_pct == pytest.approx(Decimal("0.2"), abs=Decimal("0.01"))


def test_a_real_move_is_measured_correctly():
    """Buy at $100, sell at $110: about +$10 on a $10 position, less slippage."""
    entry = buy_quote(client(FlatMarket(100))).worst_case_price
    exit_price = sell_quote(client(FlatMarket(110))).worst_case_price

    pnl = Decimal(10) * (exit_price - entry) / entry
    assert Decimal("0.90") < pnl < Decimal("1.00"), pnl
