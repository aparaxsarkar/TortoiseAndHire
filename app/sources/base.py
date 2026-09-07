"""The source-adapter contract (ADR-0004).

An adapter's whole job: turn a job board's feed into `CanonicalPosting`s. It
fetches, it parses, and that is all - no database, no business rules, no
knowledge of what happens next. `import-linter` enforces the boundary.

`fetch()` and `parse()` are deliberately split so the ingestion runner can
attribute a parse failure to a single posting (record it, skip it, continue)
rather than lose a whole batch.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import ClassVar, Protocol, Self, runtime_checkable

from pydantic import BaseModel

from app.schemas.canonical import CanonicalPosting, RawPosting
from app.sources.errors import (
    SourceAuthError,
    SourceError,
    SourcePayloadError,
    SourceRateLimited,
    SourceUnavailable,
)
from app.sources.http import HttpClient

__all__ = [
    "BaseSource",
    "HttpClient",
    "JobSource",
    "SourceAuthError",
    "SourceError",
    "SourcePayloadError",
    "SourceQuery",
    "SourceRateLimited",
    "SourceUnavailable",
]


class SourceQuery(BaseModel):
    """What to pull. `targets` is Greenhouse board tokens / Lever account slugs."""

    targets: list[str]


@runtime_checkable
class JobSource(Protocol):
    slug: ClassVar[str]

    def fetch(self, query: SourceQuery) -> AsyncIterator[RawPosting]: ...

    def parse(self, raw: RawPosting) -> CanonicalPosting: ...


class BaseSource:
    """Shared lifecycle for HTTP-backed adapters. Subclasses set `slug`,
    override `_make_http()` for per-source rate limits / base URL, and implement
    `fetch()` + `parse()`.
    """

    slug: ClassVar[str]

    def __init__(self, http: HttpClient | None = None) -> None:
        self._http = http if http is not None else self._make_http()

    def _make_http(self) -> HttpClient:
        return HttpClient()

    async def aclose(self) -> None:
        await self._http.aclose()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()
