"""GeckoTerminal OHLCV client.

Lives in `execution/` because that package is documented as the only one
that talks to the network. Nothing here trades — it reads candles.

Free tier, no API key, rate-limited on our side like every other provider.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from core.config import DataConfig
from core.logging import get_logger
from core.rate_limit import RateLimiter
from core.types import Candle
from execution.http import (
    HttpTransport,
    ProviderError,
    ProviderHttpClient,
    RetryPolicy,
    UrllibTransport,
)

logger = get_logger("tradecc.geckoterminal")

PROVIDER = "geckoterminal"
BASE_URL = "https://api.geckoterminal.com/api/v2"
MAX_LIMIT = 1000

# GeckoTerminal exposes a timeframe plus an aggregate count, so "15m" is
# ("minute", 15). Mapping explicitly beats parsing, because a silently
# mis-parsed interval would backtest a different strategy than intended.
INTERVALS: dict[str, tuple[str, int]] = {
    "1m": ("minute", 1),
    "5m": ("minute", 5),
    "15m": ("minute", 15),
    "1h": ("hour", 1),
    "4h": ("hour", 4),
    "12h": ("hour", 12),
    "1d": ("day", 1),
}


class GeckoTerminalClient:
    def __init__(
        self,
        data: DataConfig,
        network: str = "solana",
        transport: HttpTransport | None = None,
        limiter: RateLimiter | None = None,
        retry: RetryPolicy | None = None,
    ) -> None:
        self._network = network
        self._http = ProviderHttpClient(
            provider=PROVIDER,
            transport=transport or UrllibTransport(),
            limiter=limiter
            or RateLimiter(
                max_requests=data.max_requests_per_minute, per_seconds=60.0, name=PROVIDER
            ),
            retry=retry,
        )

    def fetch_candles(
        self, pool_address: str, interval: str = "15m", limit: int = 300
    ) -> list[Candle]:
        if interval not in INTERVALS:
            raise ValueError(
                f"unsupported interval {interval!r}; supported: {', '.join(INTERVALS)}"
            )
        if not 1 <= limit <= MAX_LIMIT:
            raise ValueError(f"limit must be between 1 and {MAX_LIMIT}")

        timeframe, aggregate = INTERVALS[interval]
        url = (
            f"{BASE_URL}/networks/{self._network}/pools/{pool_address}"
            f"/ohlcv/{timeframe}?aggregate={aggregate}&limit={limit}"
        )
        return _parse_candles(self._http.request("GET", url).json())


def _parse_candles(payload: Any) -> list[Candle]:
    if not isinstance(payload, dict):
        raise ProviderError(PROVIDER, "response was not a JSON object")
    try:
        rows = payload["data"]["attributes"]["ohlcv_list"]
    except (KeyError, TypeError) as exc:
        raise ProviderError(PROVIDER, "response had no ohlcv_list") from exc
    if not isinstance(rows, list):
        raise ProviderError(PROVIDER, "ohlcv_list was not a list")

    candles = [_to_candle(row) for row in rows]
    # GeckoTerminal returns newest-first. Every indicator here assumes
    # chronological order, so returning the API's order unchanged would
    # compute EMAs and RSI backwards — silently, and with plausible-looking
    # numbers. Sorting rather than reversing also survives the API changing
    # its ordering later.
    candles.sort(key=lambda candle: candle.timestamp)
    return candles


def _to_candle(row: Any) -> Candle:
    if not isinstance(row, (list, tuple)) or len(row) < 6:
        raise ProviderError(PROVIDER, f"malformed OHLCV row: {row!r}")
    try:
        timestamp = datetime.fromtimestamp(int(row[0]), tz=timezone.utc)
        # Values arrive as JSON floats; str() first so the Decimal is the
        # number as printed, not the binary approximation behind it.
        values = [Decimal(str(value)) for value in row[1:6]]
    except (TypeError, ValueError, ArithmeticError) as exc:
        raise ProviderError(PROVIDER, f"malformed OHLCV row: {row!r}") from exc

    return Candle(
        timestamp=timestamp,
        open=values[0],
        high=values[1],
        low=values[2],
        close=values[3],
        volume=values[4],
    )
