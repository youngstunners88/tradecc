"""Network contract tests — real provider APIs.

These are a DRIFT DETECTOR, not a merge gate. They run on a schedule
(.github/workflows/contract-tests.yml), never on a PR: a provider outage
says nothing about whether a diff is correct.

They assert on response *shape*, never on values. Prices move constantly;
a test that asserts on one is a test that fails for the wrong reason.
"""

from __future__ import annotations

import os
from decimal import Decimal

import pytest

from core.config import ProvidersConfig
from execution.helius import HeliusRpcClient
from execution.http import RetryPolicy
from execution.jupiter import JupiterQuoteClient

pytestmark = pytest.mark.network

SOL = "So11111111111111111111111111111111111111112"
USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"


@pytest.fixture(scope="module")
def jupiter() -> JupiterQuoteClient:
    return JupiterQuoteClient(
        providers=ProvidersConfig(), retry=RetryPolicy(max_attempts=2)
    )


def test_jupiter_free_tier_serves_quotes_without_a_key(jupiter):
    detailed = jupiter.get_quote_detailed(SOL, USDC, 10_000_000, 50, Decimal("10"))

    assert detailed.quote.expected_price > 0


@pytest.mark.parametrize(
    "field", ["inAmount", "outAmount", "otherAmountThreshold", "swapMode"]
)
def test_jupiter_quote_still_carries_the_fields_we_map(jupiter, field):
    detailed = jupiter.get_quote_detailed(SOL, USDC, 10_000_000, 50, Decimal("10"))

    assert field in detailed.raw


def test_jupiter_threshold_is_worse_than_expected_output(jupiter):
    """Our slippage cap depends on this relationship holding."""
    detailed = jupiter.get_quote_detailed(SOL, USDC, 10_000_000, 50, Decimal("10"))

    assert int(detailed.raw["otherAmountThreshold"]) <= int(detailed.raw["outAmount"])
    assert detailed.quote.worst_case_price >= detailed.quote.expected_price


def test_jupiter_honours_the_requested_slippage_bound(jupiter):
    detailed = jupiter.get_quote_detailed(SOL, USDC, 10_000_000, 50, Decimal("10"))

    # 50 bps requested; the realised bound must not exceed it materially.
    assert detailed.quote.slippage_pct <= Decimal("0.51")


@pytest.mark.skipif(
    not os.environ.get("HELIUS_API_KEY"),
    reason="HELIUS_API_KEY not set — skipping rather than failing so the "
    "keyless Jupiter checks still run",
)
def test_helius_reports_healthy():
    client = HeliusRpcClient(
        providers=ProvidersConfig(),
        api_key=os.environ["HELIUS_API_KEY"],
        retry=RetryPolicy(max_attempts=2),
    )

    assert client.get_health() == "ok"


@pytest.mark.skipif(
    not os.environ.get("HELIUS_API_KEY"), reason="HELIUS_API_KEY not set"
)
def test_helius_returns_a_blockhash():
    client = HeliusRpcClient(
        providers=ProvidersConfig(),
        api_key=os.environ["HELIUS_API_KEY"],
        retry=RetryPolicy(max_attempts=2),
    )

    assert len(client.get_latest_blockhash()) > 30
