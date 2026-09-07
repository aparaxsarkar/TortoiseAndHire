"""Source adapters: feed -> CanonicalPosting. No DB, no business logic (ADR-0004)."""

from __future__ import annotations

from app.sources.base import BaseSource, JobSource, SourceQuery
from app.sources.errors import (
    SourceAuthError,
    SourceError,
    SourcePayloadError,
    SourceRateLimited,
    SourceUnavailable,
)
from app.sources.registry import available, get_source

__all__ = [
    "BaseSource",
    "JobSource",
    "SourceAuthError",
    "SourceError",
    "SourcePayloadError",
    "SourceQuery",
    "SourceRateLimited",
    "SourceUnavailable",
    "available",
    "get_source",
]
