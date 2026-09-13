"""Client-side rate limiting for external providers.

Every provider TradeCC talks to is on a free tier — GeckoTerminal, Helius,
and Jupiter's public `lite-api` host. Free tiers do not fail politely:
they return 429s, and a bot that discovers its limit by being throttled
mid-position is finding out at the worst possible moment.

So the limit is enforced on our side, before the request goes out, for
every provider. Nothing assumes headroom it has not been granted.

The clock and sleep function are injectable so the whole thing is
testable without a test suite that actually sleeps.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from typing import Callable


class RateLimiter:
    """Sliding-window limiter: at most `max_requests` per `per_seconds`.

    A sliding window rather than a fixed one, because a fixed window lets
    a caller fire the full quota at the end of one window and again at the
    start of the next — a burst of double the intended rate, which is
    exactly what trips a provider's throttle.
    """

    def __init__(
        self,
        max_requests: int,
        per_seconds: float = 60.0,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        name: str = "provider",
    ) -> None:
        if max_requests <= 0:
            raise ValueError("max_requests must be positive")
        if per_seconds <= 0:
            raise ValueError("per_seconds must be positive")
        self._max_requests = max_requests
        self._per_seconds = per_seconds
        self._clock = clock
        self._sleep = sleep
        self._name = name
        self._hits: deque[float] = deque()
        self._lock = threading.Lock()

    @property
    def name(self) -> str:
        return self._name

    @property
    def max_requests(self) -> int:
        return self._max_requests

    def _evict_expired(self, now: float) -> None:
        cutoff = now - self._per_seconds
        while self._hits and self._hits[0] <= cutoff:
            self._hits.popleft()

    def available(self) -> int:
        """Requests that could be made right now without waiting."""
        with self._lock:
            self._evict_expired(self._clock())
            return self._max_requests - len(self._hits)

    def try_acquire(self) -> bool:
        """Take a slot if one is free. Never blocks."""
        with self._lock:
            now = self._clock()
            self._evict_expired(now)
            if len(self._hits) >= self._max_requests:
                return False
            self._hits.append(now)
            return True

    def acquire(self) -> float:
        """Take a slot, waiting if necessary. Returns seconds waited."""
        waited = 0.0
        while True:
            with self._lock:
                now = self._clock()
                self._evict_expired(now)
                if len(self._hits) < self._max_requests:
                    self._hits.append(now)
                    return waited
                # The oldest hit leaves the window at hits[0] + per_seconds.
                delay = self._hits[0] + self._per_seconds - now
            # Sleep outside the lock so other threads can make progress.
            delay = max(delay, 0.0)
            self._sleep(delay)
            waited += delay
