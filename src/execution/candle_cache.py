"""Disk cache for candle series.

A backtest that refetches from the network is neither reproducible nor
runnable offline, and re-running one against silently different data is a
good way to "discover" a strategy improvement that is really just a
different sample. Cached series make a backtest replayable exactly.

Cache entries are immutable: a given (pool, interval) key is written once
and read thereafter. Refreshing is explicit, never automatic, so a
re-run cannot quietly change its own inputs.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from core.types import Candle


class CandleCache:
    def __init__(self, cache_dir: Path | str) -> None:
        self._dir = Path(cache_dir)

    def path_for(self, pool_address: str, interval: str) -> Path:
        safe_pool = "".join(c for c in pool_address if c.isalnum() or c in "-_")
        safe_interval = "".join(c for c in interval if c.isalnum())
        return self._dir / f"{safe_pool}_{safe_interval}.json"

    def has(self, pool_address: str, interval: str) -> bool:
        return self.path_for(pool_address, interval).is_file()

    def load(self, pool_address: str, interval: str) -> list[Candle] | None:
        path = self.path_for(pool_address, interval)
        if not path.is_file():
            return None
        try:
            rows = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            # A corrupt cache entry is a cache miss, not a crash. The caller
            # refetches; nothing about correctness depends on the cache.
            return None
        try:
            return [_from_row(row) for row in rows]
        except (KeyError, TypeError, ValueError, ArithmeticError):
            return None

    def save(self, pool_address: str, interval: str, candles: list[Candle]) -> None:
        path = self.path_for(pool_address, interval)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps([_to_row(c) for c in candles], indent=2))

    def load_or_fetch(
        self, pool_address: str, interval: str, fetch, refresh: bool = False
    ) -> list[Candle]:
        """Return cached candles, fetching only on a miss or explicit refresh."""
        if not refresh:
            cached = self.load(pool_address, interval)
            if cached is not None:
                return cached
        candles = fetch()
        self.save(pool_address, interval, candles)
        return candles


def _to_row(candle: Candle) -> dict[str, str]:
    return {
        "t": candle.timestamp.isoformat(),
        # Decimals as strings: a JSON float here would reintroduce exactly
        # the rounding the rest of the codebase avoids.
        "o": str(candle.open),
        "h": str(candle.high),
        "l": str(candle.low),
        "c": str(candle.close),
        "v": str(candle.volume),
    }


def _from_row(row: dict[str, str]) -> Candle:
    timestamp = datetime.fromisoformat(row["t"])
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    return Candle(
        timestamp=timestamp,
        open=Decimal(row["o"]),
        high=Decimal(row["h"]),
        low=Decimal(row["l"]),
        close=Decimal(row["c"]),
        volume=Decimal(row["v"]),
    )
