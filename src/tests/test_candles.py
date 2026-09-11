"""Candle completeness — the boundary between a finished bar and a guess.

A bar's close price is not real until the bar ends. Acting on the
still-forming bar means deciding from data that will change, which is the
live-path form of the look-ahead bug class.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from core.candles import closes_at, completed_candles, interval_duration
from core.types import Candle

NOW = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)


def bar(offset_minutes: int) -> Candle:
    return Candle(
        timestamp=NOW + timedelta(minutes=offset_minutes),
        open=Decimal("100"),
        high=Decimal("100"),
        low=Decimal("100"),
        close=Decimal("100"),
        volume=Decimal("1"),
    )


def test_interval_duration_covers_the_supported_set():
    assert interval_duration("15m") == timedelta(minutes=15)
    assert interval_duration("1h") == timedelta(hours=1)
    assert interval_duration("1d") == timedelta(days=1)


def test_unsupported_interval_raises_rather_than_guessing():
    with pytest.raises(ValueError):
        interval_duration("7m")


def test_closes_at_is_open_plus_one_interval():
    assert closes_at(bar(0), "15m") == NOW + timedelta(minutes=15)


def test_the_in_progress_bar_is_dropped():
    """The bar opening exactly at `now` has not finished and must go."""
    series = [bar(-30), bar(-15), bar(0)]

    kept = completed_candles(series, "15m", NOW)

    assert [c.timestamp for c in kept] == [b.timestamp for b in series[:2]]


def test_a_bar_closing_exactly_at_now_is_complete():
    """Boundary: closing at `now` means it finished, so it counts."""
    kept = completed_candles([bar(-15)], "15m", NOW)

    assert len(kept) == 1


def test_everything_in_progress_yields_nothing():
    assert completed_candles([bar(0), bar(15)], "15m", NOW) == []


def test_filters_rather_than_trimming_the_tail():
    """An out-of-order in-progress bar must not slip through mid-series."""
    series = [bar(-30), bar(0), bar(-15)]

    kept = completed_candles(series, "15m", NOW)

    assert [c.timestamp for c in kept] == [bar(-30).timestamp, bar(-15).timestamp]
