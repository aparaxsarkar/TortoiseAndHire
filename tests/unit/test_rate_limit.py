from __future__ import annotations

from app.core.rate_limit import TokenBucket


def test_allows_burst_up_to_capacity() -> None:
    now = [0.0]
    bucket = TokenBucket(rate=1.0, capacity=3.0, clock=lambda: now[0])
    assert [bucket.consume() for _ in range(4)] == [True, True, True, False]


def test_refills_at_rate() -> None:
    now = [0.0]
    bucket = TokenBucket(rate=2.0, capacity=2.0, clock=lambda: now[0])
    assert bucket.consume(2.0) is True
    assert bucket.consume() is False

    now[0] = 0.5  # 0.5s * 2 tokens/s == 1 token
    assert bucket.consume() is True
    assert bucket.consume() is False


def test_never_exceeds_capacity() -> None:
    now = [0.0]
    bucket = TokenBucket(rate=100.0, capacity=5.0, clock=lambda: now[0])
    now[0] = 10.0  # would add 1000 tokens if uncapped
    assert [bucket.consume() for _ in range(6)] == [True, True, True, True, True, False]


def test_time_until() -> None:
    now = [0.0]
    bucket = TokenBucket(rate=4.0, capacity=4.0, clock=lambda: now[0])
    assert bucket.consume(4.0) is True
    assert bucket.time_until(2.0) == 0.5  # 2 tokens at 4/s
    assert bucket.time_until() == 0.25


async def test_acquire_returns_immediately_when_available() -> None:
    bucket = TokenBucket(rate=1.0, capacity=2.0)
    await bucket.acquire()  # bucket starts full; must not hang
    assert bucket.consume() is True
