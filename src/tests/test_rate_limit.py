"""Rate limiting is enforced on our side, before the request goes out.

These tests use a fake clock — the suite must never actually sleep.
"""

from __future__ import annotations

import pytest

from core.rate_limit import RateLimiter


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def time(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        # Sleeping advances the fake clock, exactly as it would in reality.
        self.now += seconds


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


def limiter(clock: FakeClock, max_requests: int = 3, per_seconds: float = 60.0) -> RateLimiter:
    return RateLimiter(
        max_requests=max_requests,
        per_seconds=per_seconds,
        clock=clock.time,
        sleep=clock.sleep,
        name="test",
    )


def test_allows_up_to_the_limit_without_waiting(clock):
    rl = limiter(clock)

    assert [rl.acquire() for _ in range(3)] == [0.0, 0.0, 0.0]
    assert clock.now == 1000.0


def test_try_acquire_refuses_past_the_limit(clock):
    rl = limiter(clock)
    for _ in range(3):
        rl.try_acquire()

    assert rl.try_acquire() is False


def test_try_acquire_never_advances_the_clock(clock):
    rl = limiter(clock)
    for _ in range(10):
        rl.try_acquire()

    assert clock.now == 1000.0


def test_acquire_waits_for_the_window_to_slide(clock):
    rl = limiter(clock)
    for _ in range(3):
        rl.acquire()

    waited = rl.acquire()

    # The oldest hit was at t=1000 and leaves the window at t=1060.
    assert waited == pytest.approx(60.0)
    assert clock.now == pytest.approx(1060.0)


def test_slots_free_up_gradually_not_all_at_once(clock):
    """A sliding window must not hand back the whole quota at once."""
    rl = limiter(clock)
    rl.acquire()
    clock.now += 10
    rl.acquire()
    clock.now += 10
    rl.acquire()

    # t=1020, hits at 1000/1010/1020. Only the first has aged out at 1060.
    clock.now = 1060.5
    assert rl.available() == 1

    rl.acquire()
    assert rl.try_acquire() is False


def test_available_reports_remaining_capacity(clock):
    rl = limiter(clock)

    assert rl.available() == 3
    rl.acquire()
    assert rl.available() == 2


def test_capacity_fully_restores_after_the_window(clock):
    rl = limiter(clock)
    for _ in range(3):
        rl.acquire()

    clock.now += 61

    assert rl.available() == 3
    assert rl.acquire() == 0.0


def test_respects_a_non_minute_window(clock):
    rl = limiter(clock, max_requests=1, per_seconds=5.0)
    rl.acquire()

    assert rl.acquire() == pytest.approx(5.0)


@pytest.mark.parametrize(
    ("max_requests", "per_seconds"), [(0, 60.0), (-1, 60.0), (5, 0.0), (5, -1.0)]
)
def test_rejects_nonsensical_limits(max_requests, per_seconds):
    with pytest.raises(ValueError):
        RateLimiter(max_requests=max_requests, per_seconds=per_seconds)
