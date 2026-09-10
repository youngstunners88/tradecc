"""Live SOL price client — offline, against a fake transport.

Every SOL-denominated cost scales with this number, so the failure that
matters is a bad price being accepted quietly rather than raising.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from core.config import ProvidersConfig
from core.rate_limit import RateLimiter
from execution.http import ProviderError, RetryPolicy
from execution.sol_price import WRAPPED_SOL_MINT, SolPriceClient
from tests.test_http import FakeTransport, response

PAYLOAD = {
    WRAPPED_SOL_MINT: {
        "usdPrice": 102.00042105865879,
        "decimals": 9,
        "priceChange24h": -1.938,
    }
}


def make_client(transport) -> SolPriceClient:
    return SolPriceClient(
        providers=ProvidersConfig(),
        transport=transport,
        limiter=RateLimiter(1000, 60.0, name="jupiter-price"),
        retry=RetryPolicy(max_attempts=1),
    )


def test_reads_the_usd_price():
    price = make_client(FakeTransport(response(200, PAYLOAD))).get_price_usd()

    assert price == Decimal("102.00042105865879")


def test_price_is_decimal_not_float():
    """A float here would import rounding error into every cost at once."""
    price = make_client(FakeTransport(response(200, PAYLOAD))).get_price_usd()

    assert isinstance(price, Decimal)
    # Exact: parsed via str, so the value is not a binary approximation.
    assert str(price) == "102.00042105865879"


def test_missing_mint_entry_raises():
    with pytest.raises(ProviderError):
        make_client(FakeTransport(response(200, {}))).get_price_usd()


def test_missing_usd_price_field_raises():
    payload = {WRAPPED_SOL_MINT: {"decimals": 9}}

    with pytest.raises(ProviderError):
        make_client(FakeTransport(response(200, payload))).get_price_usd()


@pytest.mark.parametrize("bad", [0, -5, "0"])
def test_non_positive_price_raises_rather_than_zeroing_costs(bad):
    """A zero price would silently make every SOL-denominated cost free."""
    payload = {WRAPPED_SOL_MINT: {"usdPrice": bad}}

    with pytest.raises(ProviderError):
        make_client(FakeTransport(response(200, payload))).get_price_usd()


def test_non_numeric_price_raises():
    payload = {WRAPPED_SOL_MINT: {"usdPrice": "not-a-number"}}

    with pytest.raises(ProviderError):
        make_client(FakeTransport(response(200, payload))).get_price_usd()


def test_non_object_payload_raises():
    with pytest.raises(ProviderError):
        make_client(FakeTransport(response(200, ["unexpected"]))).get_price_usd()
