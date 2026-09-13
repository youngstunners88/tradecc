"""Candle interval arithmetic and completeness.

`Candle.timestamp` is the bar's **open** time, so a bar is only finished
once `timestamp + interval` has passed. That distinction is the whole
reason this module exists: a provider asked for recent OHLCV returns the
*current, still-forming* bar alongside the completed ones, and its
"close" is just the live price. Acting on it means deciding from a bar
that has not happened yet, and the decision changes every time you poll.

Backtests never hit this — they replay finished history — so using an
in-progress bar live would make paper evidence come from a different
process than the one the backtest validated.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Sequence

from core.types import Candle

# Mirrors the intervals the data layer supports. Mapping explicitly beats
# parsing: a silently mis-parsed interval would mis-judge completeness.
INTERVAL_SECONDS: dict[str, int] = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "1h": 3600,
    "4h": 14400,
    "12h": 43200,
    "1d": 86400,
}


def interval_duration(interval: str) -> timedelta:
    if interval not in INTERVAL_SECONDS:
        raise ValueError(
            f"unsupported interval {interval!r}; "
            f"supported: {', '.join(INTERVAL_SECONDS)}"
        )
    return timedelta(seconds=INTERVAL_SECONDS[interval])


def closes_at(candle: Candle, interval: str) -> datetime:
    """When this bar finishes — the moment its close price becomes real."""
    return candle.timestamp + interval_duration(interval)


def completed_candles(
    candles: Sequence[Candle], interval: str, now: datetime
) -> list[Candle]:
    """Drop any bar that has not finished by `now`.

    Filters rather than trimming the tail, so an out-of-order or duplicated
    trailing bar cannot smuggle an unfinished one through.
    """
    duration = interval_duration(interval)
    return [c for c in candles if c.timestamp + duration <= now]
