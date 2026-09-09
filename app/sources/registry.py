"""slug -> adapter. The ingestion service resolves a source by slug through here."""

from __future__ import annotations

from collections.abc import Callable

from app.sources.ashby import AshbySource
from app.sources.base import JobSource
from app.sources.errors import SourceError
from app.sources.greenhouse import GreenhouseSource
from app.sources.lever import LeverSource
from app.sources.workday import WorkdaySource

_SOURCES: dict[str, Callable[[], JobSource]] = {
    GreenhouseSource.slug: GreenhouseSource,
    LeverSource.slug: LeverSource,
    AshbySource.slug: AshbySource,
    WorkdaySource.slug: WorkdaySource,
}


def available() -> list[str]:
    return sorted(_SOURCES)


def get_source(slug: str) -> JobSource:
    try:
        factory = _SOURCES[slug]
    except KeyError:
        raise SourceError(f"unknown source: {slug!r} (have: {', '.join(available())})") from None
    return factory()
