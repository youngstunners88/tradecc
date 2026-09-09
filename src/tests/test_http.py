"""Transport, retry, and backoff — tested without a network or a real sleep."""

from __future__ import annotations

import json

import pytest

from core.rate_limit import RateLimiter
from execution.http import (
    HttpResponse,
    ProviderError,
    ProviderHttpClient,
    RetryPolicy,
    TransportError,
)


class FakeTransport:
    """Returns queued responses; raises queued exceptions. Records requests."""

    def __init__(self, *responses) -> None:
        self._queue = list(responses)
        self.requests: list[tuple[str, str]] = []

    def request(self, method, url, *, headers=None, body=None, timeout=None) -> HttpResponse:
        self.requests.append((method, url))
        if not self._queue:
            raise AssertionError("FakeTransport ran out of queued responses")
        item = self._queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    @property
    def call_count(self) -> int:
        return len(self.requests)


def response(status: int = 200, payload=None, headers=None) -> HttpResponse:
    return HttpResponse(
        status=status,
        body=json.dumps(payload if payload is not None else {"ok": True}).encode(),
        headers=headers or {},
    )


@pytest.fixture
def slept() -> list[float]:
    return []


def client(transport, slept, retry: RetryPolicy | None = None) -> ProviderHttpClient:
    return ProviderHttpClient(
        provider="test",
        transport=transport,
        limiter=RateLimiter(1000, 60.0, name="test"),
        retry=retry or RetryPolicy(max_attempts=3, initial_backoff_seconds=0.5),
        sleep=slept.append,
    )


def test_returns_a_successful_response(slept):
    transport = FakeTransport(response(200, {"value": 1}))

    result = client(transport, slept).request("GET", "https://x.test/a")

    assert result.json() == {"value": 1}
    assert slept == []


def test_retries_a_500_then_succeeds(slept):
    transport = FakeTransport(response(500), response(200, {"value": 2}))

    result = client(transport, slept).request("GET", "https://x.test/a")

    assert result.json() == {"value": 2}
    assert transport.call_count == 2
    assert slept == [0.5]


def test_retries_a_transport_error(slept):
    transport = FakeTransport(TransportError("connection reset"), response(200))

    client(transport, slept).request("GET", "https://x.test/a")

    assert transport.call_count == 2


def test_gives_up_after_max_attempts(slept):
    transport = FakeTransport(response(503), response(503), response(503))

    with pytest.raises(ProviderError, match="after 3 attempts"):
        client(transport, slept).request("GET", "https://x.test/a")

    assert transport.call_count == 3


def test_backoff_grows_exponentially(slept):
    transport = FakeTransport(response(500), response(500), response(500))

    with pytest.raises(ProviderError):
        client(transport, slept).request("GET", "https://x.test/a")

    assert slept == [0.5, 1.0]


def test_backoff_is_capped(slept):
    policy = RetryPolicy(
        max_attempts=5, initial_backoff_seconds=4.0, backoff_multiplier=10.0,
        max_backoff_seconds=8.0,
    )
    transport = FakeTransport(*[response(500) for _ in range(5)])

    with pytest.raises(ProviderError):
        client(transport, slept, policy).request("GET", "https://x.test/a")

    assert max(slept) == 8.0


def test_does_not_retry_a_400(slept):
    transport = FakeTransport(response(400))

    with pytest.raises(ProviderError, match="HTTP 400"):
        client(transport, slept).request("GET", "https://x.test/a")

    assert transport.call_count == 1


def test_does_not_retry_a_404(slept):
    transport = FakeTransport(response(404))

    with pytest.raises(ProviderError):
        client(transport, slept).request("GET", "https://x.test/a")

    assert transport.call_count == 1


def test_retries_a_429(slept):
    transport = FakeTransport(response(429), response(200))

    client(transport, slept).request("GET", "https://x.test/a")

    assert transport.call_count == 2


def test_honours_retry_after_header(slept):
    """The provider knows its own throttle better than our backoff curve."""
    transport = FakeTransport(response(429, headers={"retry-after": "3"}), response(200))

    client(transport, slept).request("GET", "https://x.test/a")

    assert slept == [3.0]


def test_ignores_an_unparseable_retry_after(slept):
    transport = FakeTransport(response(429, headers={"retry-after": "soon"}), response(200))

    client(transport, slept).request("GET", "https://x.test/a")

    assert slept == [0.5]


def test_retry_after_is_capped_by_policy(slept):
    transport = FakeTransport(response(429, headers={"retry-after": "9999"}), response(200))

    client(transport, slept).request("GET", "https://x.test/a")

    assert slept == [8.0]


def test_rate_limiter_applies_to_every_attempt_including_retries(slept):
    """A retry storm that ignores the limiter turns a 429 into a ban."""
    limiter = RateLimiter(1000, 60.0, name="test")
    transport = FakeTransport(response(500), response(200))
    ProviderHttpClient(
        provider="test", transport=transport, limiter=limiter,
        retry=RetryPolicy(max_attempts=3), sleep=slept.append,
    ).request("GET", "https://x.test/a")

    assert limiter.available() == 998


def test_malformed_json_raises_provider_error(slept):
    transport = FakeTransport(HttpResponse(200, b"not json", {}))

    with pytest.raises(ProviderError, match="not valid JSON"):
        client(transport, slept).request("GET", "https://x.test/a").json()


def test_real_url_is_never_logged_when_redacted_url_given(slept, caplog):
    transport = FakeTransport(response(500), response(200))

    with caplog.at_level("WARNING", logger="tradecc.http"):
        client(transport, slept).request(
            "GET", "https://x.test/a?api-key=SUPERSECRET", redacted_url="https://x.test/a?api-key=***"
        )

    assert "SUPERSECRET" not in caplog.text
    # The request itself still used the real URL.
    assert "SUPERSECRET" in transport.requests[0][1]
