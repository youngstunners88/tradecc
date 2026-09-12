"""GeckoTerminal parsing and the candle cache — offline."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from core.config import DataConfig
from core.rate_limit import RateLimiter
from core.types import Candle
from execution.candle_cache import CandleCache
from execution.geckoterminal import GeckoTerminalClient
from execution.http import ProviderError, RetryPolicy
from tests.test_http import FakeTransport, response

POOL = "8sLbNZoA1cfnvMJLPfp98ZLAnFSYCFApfJKMbiXNLwxj"

# As the live API returns it: newest first.
PAYLOAD = {
    "data": {
        "attributes": {
            "ohlcv_list": [
                [1788958800, 104.8, 105.05, 103.81, 104.45, 9260.9],
                [1788955200, 104.05, 105.2, 104.0, 104.8, 11148.5],
                [1788951600, 103.49, 104.34, 103.15, 104.05, 9156.1],
            ]
        }
    }
}


def make_client(transport) -> GeckoTerminalClient:
    return GeckoTerminalClient(
        data=DataConfig(),
        transport=transport,
        limiter=RateLimiter(1000, 60.0, name="gt"),
        retry=RetryPolicy(max_attempts=1),
    )


def test_parses_candles():
    result = make_client(FakeTransport(response(200, PAYLOAD))).fetch_candles(POOL, "1h")

    assert len(result) == 3
    assert all(isinstance(c, Candle) for c in result)


def test_reverses_the_api_order_into_chronological():
    """The API returns newest-first; indicators assume the opposite.

    Passing the API order straight through would compute EMAs and RSI
    backwards — silently, with plausible-looking numbers.
    """
    result = make_client(FakeTransport(response(200, PAYLOAD))).fetch_candles(POOL, "1h")

    assert [c.timestamp for c in result] == sorted(c.timestamp for c in result)
    assert result[0].timestamp < result[-1].timestamp


def test_maps_ohlcv_fields_in_the_right_order():
    result = make_client(FakeTransport(response(200, PAYLOAD))).fetch_candles(POOL, "1h")
    oldest = result[0]

    assert oldest.open == Decimal("103.49")
    assert oldest.high == Decimal("104.34")
    assert oldest.low == Decimal("103.15")
    assert oldest.close == Decimal("104.05")
    assert oldest.volume == Decimal("9156.1")


def test_timestamps_are_utc_aware():
    result = make_client(FakeTransport(response(200, PAYLOAD))).fetch_candles(POOL, "1h")

    assert result[0].timestamp.tzinfo is timezone.utc


def test_floats_become_exact_decimals():
    """str() first, so the Decimal is the printed number not the binary one."""
    payload = {"data": {"attributes": {"ohlcv_list": [[1788958800, 0.1, 0.2, 0.05, 0.3, 1.0]]}}}

    result = make_client(FakeTransport(response(200, payload))).fetch_candles(POOL, "1h")

    assert result[0].open == Decimal("0.1")
    assert result[0].close == Decimal("0.3")


def test_builds_the_expected_url():
    transport = FakeTransport(response(200, PAYLOAD))

    make_client(transport).fetch_candles(POOL, "15m", limit=100)

    _, url = transport.requests[0]
    assert "/networks/solana/pools/" in url
    assert "/ohlcv/minute?aggregate=15" in url
    assert "limit=100" in url


def test_unsupported_interval_is_rejected():
    with pytest.raises(ValueError, match="unsupported interval"):
        make_client(FakeTransport()).fetch_candles(POOL, "7m")


@pytest.mark.parametrize("limit", [0, -1, 5000])
def test_out_of_range_limit_is_rejected(limit):
    with pytest.raises(ValueError, match="limit"):
        make_client(FakeTransport()).fetch_candles(POOL, "1h", limit=limit)


def test_missing_ohlcv_list_raises():
    with pytest.raises(ProviderError, match="ohlcv_list"):
        make_client(FakeTransport(response(200, {"data": {}}))).fetch_candles(POOL, "1h")


def test_malformed_row_raises():
    payload = {"data": {"attributes": {"ohlcv_list": [[1788958800, 1.0]]}}}

    with pytest.raises(ProviderError, match="malformed"):
        make_client(FakeTransport(response(200, payload))).fetch_candles(POOL, "1h")


def test_empty_series_is_not_an_error():
    payload = {"data": {"attributes": {"ohlcv_list": []}}}

    assert make_client(FakeTransport(response(200, payload))).fetch_candles(POOL, "1h") == []


# --- cache ---


def sample_candles() -> list[Candle]:
    return [
        Candle(
            timestamp=datetime(2026, 9, 1, h, tzinfo=timezone.utc),
            open=Decimal("1.5"),
            high=Decimal("2.25"),
            low=Decimal("1.0"),
            close=Decimal("2.0"),
            volume=Decimal("100.125"),
        )
        for h in range(3)
    ]


def test_cache_round_trips_exactly(tmp_path):
    cache = CandleCache(tmp_path)
    original = sample_candles()

    cache.save(POOL, "1h", original)

    assert cache.load(POOL, "1h") == original


def test_cache_miss_returns_none(tmp_path):
    assert CandleCache(tmp_path).load(POOL, "1h") is None


def test_load_or_fetch_uses_the_network_only_on_a_miss(tmp_path):
    cache = CandleCache(tmp_path)
    calls = []

    def fetch():
        calls.append(1)
        return sample_candles()

    first = cache.load_or_fetch(POOL, "1h", fetch)
    second = cache.load_or_fetch(POOL, "1h", fetch)

    assert first == second
    assert len(calls) == 1


def test_refresh_forces_a_refetch(tmp_path):
    cache = CandleCache(tmp_path)
    calls = []

    def fetch():
        calls.append(1)
        return sample_candles()

    cache.load_or_fetch(POOL, "1h", fetch)
    cache.load_or_fetch(POOL, "1h", fetch, refresh=True)

    assert len(calls) == 2


def test_corrupt_cache_is_a_miss_not_a_crash(tmp_path):
    cache = CandleCache(tmp_path)
    cache.save(POOL, "1h", sample_candles())
    cache.path_for(POOL, "1h").write_text("{ not json")

    assert cache.load(POOL, "1h") is None


def test_cache_path_is_sanitised(tmp_path):
    """A pool address must never escape the cache directory."""
    path = CandleCache(tmp_path).path_for("../../etc/passwd", "1h")

    assert tmp_path in path.parents
    assert ".." not in path.name


def test_non_finite_ohlcv_is_a_provider_error():
    """json.loads parses bare NaN/Infinity. A NaN close would propagate into
    every indicator and produce silence or nonsense rather than an error."""
    import pytest as _pytest

    from execution.geckoterminal import _to_candle
    from execution.http import ProviderError

    with _pytest.raises(ProviderError):
        _to_candle([1757000000, float("nan"), 1, 1, 1, 1])
    with _pytest.raises(ProviderError):
        _to_candle([1757000000, 1, float("inf"), 1, 1, 1])
