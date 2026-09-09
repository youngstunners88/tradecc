"""Jupiter quote mapping — offline, against a fake transport."""

from __future__ import annotations

from decimal import Decimal

import pytest

from core.config import ProvidersConfig
from core.rate_limit import RateLimiter
from core.types import Side
from execution.http import ProviderError, RetryPolicy
from execution.jupiter import JupiterQuoteClient
from tests.test_http import FakeTransport, response

TOKEN = "So11111111111111111111111111111111111111112"
USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"

QUOTE_PAYLOAD = {
    "inputMint": USDC,
    "inAmount": "10000000",
    "outputMint": TOKEN,
    "outAmount": "1000000",
    "otherAmountThreshold": "995000",
    "swapMode": "ExactIn",
    "slippageBps": 50,
}


def make_client(transport, retry: RetryPolicy | None = None) -> JupiterQuoteClient:
    return JupiterQuoteClient(
        providers=ProvidersConfig(),
        transport=transport,
        limiter=RateLimiter(1000, 60.0, name="jupiter"),
        retry=retry or RetryPolicy(max_attempts=1),
    )


def get_quote(transport, **overrides):
    kwargs = {
        "input_mint": USDC,
        "output_mint": TOKEN,
        "amount_atomic": 10_000_000,
        "slippage_bps": 50,
        "amount_usd": Decimal("10"),
        **overrides,
    }
    return make_client(transport).get_quote(**kwargs)


def test_maps_a_quote_into_the_domain_type():
    quote = get_quote(FakeTransport(response(200, QUOTE_PAYLOAD)))

    assert quote.token_mint == TOKEN
    assert quote.side is Side.BUY
    assert quote.amount_usd == Decimal("10")
    assert quote.source == "jupiter"


def test_worst_case_price_comes_from_other_amount_threshold():
    """The threshold is the number the risk engine's slippage cap reads."""
    quote = get_quote(FakeTransport(response(200, QUOTE_PAYLOAD)))

    assert quote.expected_price == Decimal(10_000_000) / Decimal(1_000_000)
    assert quote.worst_case_price == Decimal(10_000_000) / Decimal(995_000)
    assert quote.worst_case_price > quote.expected_price


def test_slippage_pct_matches_the_quoted_threshold():
    quote = get_quote(FakeTransport(response(200, QUOTE_PAYLOAD)))

    # 1_000_000 -> 995_000 is a 0.5025...% worse fill.
    assert quote.slippage_pct == pytest.approx(Decimal("0.50251"), abs=Decimal("0.0001"))


def test_a_quote_with_no_slippage_reports_zero():
    payload = {**QUOTE_PAYLOAD, "otherAmountThreshold": "1000000"}

    quote = get_quote(FakeTransport(response(200, payload)))

    assert quote.slippage_pct == Decimal("0")


def test_builds_the_expected_request_url():
    transport = FakeTransport(response(200, QUOTE_PAYLOAD))

    get_quote(transport)

    method, url = transport.requests[0]
    assert method == "GET"
    assert url.startswith("https://lite-api.jup.ag/swap/v1/quote?")
    assert f"inputMint={USDC}" in url
    assert "amount=10000000" in url
    assert "slippageBps=50" in url


def test_defaults_to_the_free_public_host():
    assert ProvidersConfig().jupiter_base_url == "https://lite-api.jup.ag"


@pytest.mark.parametrize("field", ["inAmount", "outAmount", "otherAmountThreshold"])
def test_missing_required_field_raises(field):
    payload = {k: v for k, v in QUOTE_PAYLOAD.items() if k != field}

    with pytest.raises(ProviderError, match=field):
        get_quote(FakeTransport(response(200, payload)))


def test_non_integer_amount_raises():
    payload = {**QUOTE_PAYLOAD, "outAmount": "not-a-number"}

    with pytest.raises(ProviderError, match="outAmount"):
        get_quote(FakeTransport(response(200, payload)))


def test_zero_output_raises_rather_than_dividing_by_zero():
    payload = {**QUOTE_PAYLOAD, "outAmount": "0"}

    with pytest.raises(ProviderError, match="non-positive"):
        get_quote(FakeTransport(response(200, payload)))


def test_non_object_response_raises():
    with pytest.raises(ProviderError, match="not a JSON object"):
        get_quote(FakeTransport(response(200, ["unexpected"])))


@pytest.mark.parametrize("amount", [0, -1])
def test_rejects_non_positive_amount(amount):
    with pytest.raises(ValueError, match="amount_atomic"):
        get_quote(FakeTransport(response(200, QUOTE_PAYLOAD)), amount_atomic=amount)


def test_rejects_negative_slippage():
    with pytest.raises(ValueError, match="slippage_bps"):
        get_quote(FakeTransport(response(200, QUOTE_PAYLOAD)), slippage_bps=-1)


def test_detailed_quote_exposes_the_raw_payload():
    client = make_client(FakeTransport(response(200, QUOTE_PAYLOAD)))

    detailed = client.get_quote_detailed(USDC, TOKEN, 10_000_000, 50, Decimal("10"))

    assert detailed.raw["swapMode"] == "ExactIn"


def test_mock_and_real_client_are_substitutable():
    """The seam only works if both sides genuinely satisfy the protocol."""
    from execution.client import QuoteSource
    from execution.mock import MockQuoteSource

    real: QuoteSource = make_client(FakeTransport(response(200, QUOTE_PAYLOAD)))
    fake: QuoteSource = MockQuoteSource()

    args = (USDC, TOKEN, 10_000_000, 50, Decimal("10"))
    for source in (real, fake):
        quote = source.get_quote(*args)
        assert quote.token_mint == TOKEN
        assert quote.worst_case_price >= quote.expected_price

    assert isinstance(real, QuoteSource)
    assert isinstance(fake, QuoteSource)


def test_client_has_no_swap_or_send_method():
    """Stage 2 is quote-only: no path here can build or send a transaction."""
    surface = {name for name in dir(JupiterQuoteClient) if not name.startswith("_")}

    assert surface == {"get_quote", "get_quote_detailed"}
