from __future__ import annotations

import pytest

from app.core.retry import async_retry_policy, retry_policy

# initial/max backoff 0.0 -> wait_exponential_jitter yields 0s, so tests are fast.
FAST = {"initial_backoff": 0.0, "max_backoff": 0.0}


def test_retries_then_succeeds() -> None:
    calls = {"n": 0}

    def flaky() -> str:
        calls["n"] += 1
        if calls["n"] < 3:
            raise ValueError("boom")
        return "ok"

    result = retry_policy(max_attempts=5, **FAST)(flaky)
    assert result == "ok"
    assert calls["n"] == 3


def test_reraises_original_after_max_attempts() -> None:
    calls = {"n": 0}

    def always_fails() -> None:
        calls["n"] += 1
        raise RuntimeError("nope")

    with pytest.raises(RuntimeError, match="nope"):
        retry_policy(max_attempts=3, **FAST)(always_fails)
    assert calls["n"] == 3


def test_does_not_retry_unlisted_exception() -> None:
    calls = {"n": 0}

    def raises_type_error() -> None:
        calls["n"] += 1
        raise TypeError

    with pytest.raises(TypeError):
        retry_policy(max_attempts=3, retry_on=ValueError, **FAST)(raises_type_error)
    assert calls["n"] == 1


async def test_async_retries_then_succeeds() -> None:
    calls = {"n": 0}

    async def flaky() -> str:
        calls["n"] += 1
        if calls["n"] < 2:
            raise ValueError
        return "ok"

    result = await async_retry_policy(max_attempts=3, **FAST)(flaky)
    assert result == "ok"
    assert calls["n"] == 2
