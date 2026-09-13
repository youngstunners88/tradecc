"""Live SOL/USD price.

Every SOL-denominated cost — base fee, priority fee, Jito tip, account
rent — scales with this number, so a stale one misprices all of them at
once and in the same direction. The config default said 200 while SOL
traded near 102, which overstated those costs by nearly 2x.

Reads Jupiter's price endpoint on the same free public host as the quote
client, behind the same rate limiter. Backtests of a SOL-quoted pair do
not need this at all: the bar's own close is the SOL price, and using it
is both exact and offline.
"""

from __future__ import annotations

import urllib.parse
from decimal import Decimal, InvalidOperation
from typing import Any

from core.config import ProvidersConfig
from core.logging import get_logger
from core.rate_limit import RateLimiter
from execution.http import (
    HttpTransport,
    ProviderError,
    ProviderHttpClient,
    RetryPolicy,
    UrllibTransport,
)

logger = get_logger("tradecc.sol_price")

PROVIDER = "jupiter-price"
WRAPPED_SOL_MINT = "So11111111111111111111111111111111111111112"


class SolPriceClient:
    def __init__(
        self,
        providers: ProvidersConfig,
        transport: HttpTransport | None = None,
        limiter: RateLimiter | None = None,
        retry: RetryPolicy | None = None,
    ) -> None:
        self._base_url = providers.jupiter_base_url
        self._http = ProviderHttpClient(
            provider=PROVIDER,
            transport=transport or UrllibTransport(),
            limiter=limiter
            or RateLimiter(
                max_requests=providers.jupiter_max_requests_per_minute,
                per_seconds=60.0,
                name=PROVIDER,
            ),
            retry=retry,
        )

    def get_price_usd(self, mint: str = WRAPPED_SOL_MINT) -> Decimal:
        query = urllib.parse.urlencode({"ids": mint})
        url = f"{self._base_url}/price/v3?{query}"
        return _parse_price(self._http.request("GET", url).json(), mint)


def _parse_price(payload: Any, mint: str) -> Decimal:
    if not isinstance(payload, dict):
        raise ProviderError(PROVIDER, "price response was not a JSON object")
    entry = payload.get(mint)
    if not isinstance(entry, dict):
        raise ProviderError(PROVIDER, f"price response missing entry for {mint!r}")
    raw = entry.get("usdPrice")
    if raw is None:
        raise ProviderError(PROVIDER, "price entry missing 'usdPrice'")
    try:
        # Via str: the payload carries a JSON float, and converting it
        # directly would import binary rounding error into a number that
        # multiplies every cost in the model.
        price = Decimal(str(raw))
    except InvalidOperation:
        raise ProviderError(PROVIDER, f"'usdPrice' was not a number: {raw!r}") from None
    if price <= 0:
        raise ProviderError(PROVIDER, f"'usdPrice' was not positive: {price}")
    return price
