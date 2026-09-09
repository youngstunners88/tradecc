"""HTTP transport and retry policy for provider clients.

The transport is a protocol with an injectable implementation. That seam
is the whole reason the unit suite cannot reach the network: tests pass a
fake that returns canned payloads, so there is no ambient client able to
make a real request even by accident.

Mocking at the *client* level instead would leave retry, backoff, and
rate-limit handling untested — which is exactly where the bugs live.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Protocol

from core.logging import get_logger
from core.rate_limit import RateLimiter

logger = get_logger("tradecc.http")

DEFAULT_TIMEOUT_SECONDS = 15.0
DEFAULT_USER_AGENT = "tradecc/0.1 (+https://github.com/youngstunners88/tradecc)"
RETRYABLE_STATUS = frozenset({408, 425, 429, 500, 502, 503, 504})


class TransportError(Exception):
    """A request never produced an HTTP response (DNS, timeout, reset)."""


class ProviderError(Exception):
    """A provider request failed and will not be retried further."""

    def __init__(self, provider: str, message: str, status: int | None = None) -> None:
        super().__init__(f"{provider}: {message}")
        self.provider = provider
        self.status = status


@dataclass(frozen=True)
class HttpResponse:
    status: int
    body: bytes
    headers: dict[str, str]

    def json(self) -> Any:
        try:
            return json.loads(self.body)
        except json.JSONDecodeError as exc:
            raise ProviderError("http", f"response was not valid JSON: {exc}") from exc

    @property
    def is_retryable(self) -> bool:
        return self.status in RETRYABLE_STATUS

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300


class HttpTransport(Protocol):
    def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        body: bytes | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> HttpResponse: ...


class UrllibTransport:
    """Real transport, on the standard library.

    No third-party HTTP dependency: for a money-adjacent project, a smaller
    supply-chain surface is worth more than the ergonomics of a nicer
    client, and everything above this class is transport-agnostic anyway.
    """

    def __init__(self, user_agent: str = DEFAULT_USER_AGENT) -> None:
        self._user_agent = user_agent

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        body: bytes | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> HttpResponse:
        request = urllib.request.Request(url, data=body, method=method)
        # urllib's default User-Agent ("Python-urllib/3.x") is rejected
        # outright by some providers — GeckoTerminal answers it with a 403.
        # Identifying ourselves is both a fix and good manners on a free tier.
        request.add_header("User-Agent", self._user_agent)
        request.add_header("Accept", "application/json")
        for key, value in (headers or {}).items():
            request.add_header(key, value)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return HttpResponse(
                    status=response.status,
                    body=response.read(),
                    headers={k.lower(): v for k, v in response.headers.items()},
                )
        except urllib.error.HTTPError as exc:
            # An HTTP error is still a response — the caller decides whether
            # the status is retryable, so it must not surface as a transport
            # failure.
            return HttpResponse(
                status=exc.code,
                body=exc.read(),
                headers={k.lower(): v for k, v in (exc.headers or {}).items()},
            )
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise TransportError(str(exc)) from exc


@dataclass(frozen=True)
class RetryPolicy:
    """Exponential backoff. Deterministic by default so tests can assert on it."""

    max_attempts: int = 3
    initial_backoff_seconds: float = 0.5
    backoff_multiplier: float = 2.0
    max_backoff_seconds: float = 8.0

    def backoff_for(self, attempt: int) -> float:
        """Delay before retrying after `attempt` failures (1-indexed)."""
        delay = self.initial_backoff_seconds * (self.backoff_multiplier ** (attempt - 1))
        return min(delay, self.max_backoff_seconds)


class ProviderHttpClient:
    """Shared provider plumbing: rate limit, retry, backoff, error mapping.

    Rate limiting happens before every attempt, retries included — a retry
    storm that ignores the limiter is how a transient 429 becomes a ban.
    """

    def __init__(
        self,
        provider: str,
        transport: HttpTransport,
        limiter: RateLimiter,
        retry: RetryPolicy | None = None,
        sleep: Callable[[float], None] = time.sleep,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self._provider = provider
        self._transport = transport
        self._limiter = limiter
        self._retry = retry or RetryPolicy()
        self._sleep = sleep
        self._timeout = timeout

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        body: bytes | None = None,
        redacted_url: str | None = None,
    ) -> HttpResponse:
        """Make a request, retrying transient failures.

        `redacted_url` is what gets logged. Provider URLs can carry an API
        key in the query string, so the real URL is never logged.
        """
        loggable = redacted_url or url
        last_error: str = "no attempts made"

        for attempt in range(1, self._retry.max_attempts + 1):
            self._limiter.acquire()
            try:
                response = self._transport.request(
                    method, url, headers=headers, body=body, timeout=self._timeout
                )
            except TransportError as exc:
                last_error = f"transport error: {exc}"
                response = None
            else:
                if response.ok:
                    return response
                last_error = f"HTTP {response.status}"
                if not response.is_retryable:
                    raise ProviderError(self._provider, last_error, response.status)

            if attempt == self._retry.max_attempts:
                break

            delay = self._backoff_seconds(attempt, response)
            logger.warning(
                "provider_request_retry",
                extra={
                    "provider": self._provider,
                    "url": loggable,
                    "attempt": attempt,
                    "max_attempts": self._retry.max_attempts,
                    "error": last_error,
                    "backoff_seconds": delay,
                },
            )
            self._sleep(delay)

        raise ProviderError(
            self._provider,
            f"{last_error} after {self._retry.max_attempts} attempts ({loggable})",
        )

    def _backoff_seconds(self, attempt: int, response: HttpResponse | None) -> float:
        """Honour Retry-After when the provider sends one — it knows better."""
        if response is not None:
            retry_after = response.headers.get("retry-after")
            if retry_after:
                try:
                    return max(0.0, min(float(retry_after), self._retry.max_backoff_seconds))
                except ValueError:
                    pass
        return self._retry.backoff_for(attempt)
