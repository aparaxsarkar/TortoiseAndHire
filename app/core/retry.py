"""Retry policies.

Thin factories over `tenacity` so retry behaviour is declared in one place and
tuned per call site. Both return a callable object: pass it your function and
it runs it with retries.

    result = retry_policy(retry_on=SourceUnavailable)(adapter.fetch, query)

Exponential backoff with jitter, capped, and `reraise=True` so the *original*
exception surfaces after the last attempt (not tenacity's RetryError wrapper).
HTTP-specific concerns like honouring a `Retry-After` header are layered on in
`app/sources/http.py` when that exists.
"""

from __future__ import annotations

import tenacity

DEFAULT_MAX_ATTEMPTS = 4
DEFAULT_INITIAL_BACKOFF = 1.0
DEFAULT_MAX_BACKOFF = 30.0


def retry_policy(
    *,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    initial_backoff: float = DEFAULT_INITIAL_BACKOFF,
    max_backoff: float = DEFAULT_MAX_BACKOFF,
    retry_on: type[BaseException] | tuple[type[BaseException], ...] = Exception,
) -> tenacity.Retrying:
    return tenacity.Retrying(
        stop=tenacity.stop_after_attempt(max_attempts),
        wait=tenacity.wait_exponential_jitter(initial=initial_backoff, max=max_backoff),
        retry=tenacity.retry_if_exception_type(retry_on),
        reraise=True,
    )


def async_retry_policy(
    *,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    initial_backoff: float = DEFAULT_INITIAL_BACKOFF,
    max_backoff: float = DEFAULT_MAX_BACKOFF,
    retry_on: type[BaseException] | tuple[type[BaseException], ...] = Exception,
) -> tenacity.AsyncRetrying:
    return tenacity.AsyncRetrying(
        stop=tenacity.stop_after_attempt(max_attempts),
        wait=tenacity.wait_exponential_jitter(initial=initial_backoff, max=max_backoff),
        retry=tenacity.retry_if_exception_type(retry_on),
        reraise=True,
    )
