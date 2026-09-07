"""Adapter failure taxonomy. The ingestion runner maps each to a pipeline stage."""

from __future__ import annotations

from app.core.errors import TortoiseError


class SourceError(TortoiseError):
    """Base for adapter failures."""


class SourceUnavailable(SourceError):
    """5xx, timeout, or transport error - retryable."""


class SourceRateLimited(SourceError):
    """429. `retry_after` is seconds, when the server told us."""

    def __init__(self, message: str = "rate limited", *, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class SourceAuthError(SourceError):
    """401 / 403 - abort the run, do not retry."""


class SourcePayloadError(SourceError):
    """A response could not be parsed into a posting - skip this one."""
