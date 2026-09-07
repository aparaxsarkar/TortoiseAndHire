"""The persistence seam (ADR-0011).

The runner never imports the ORM. It writes through these three ports; the
concrete, repository-backed implementations live one layer up in
`app/services/ingestion.py`, and the unit tests pass in-memory fakes.

Keeping the seam this narrow is what enforces write-ownership: a `SourcePostingSink`
can touch `companies` / `jobs` / `source_postings`, a `FilteredPostingSink` only
`filtered_postings`, and neither can reach `applications` even by accident.
"""

from __future__ import annotations

import enum
import uuid
from contextlib import AbstractContextManager
from typing import Any, Protocol

from app.deduplication.identity import PostingIdentity
from app.discovery.rules import RelevanceVerdict
from app.ingestion.results import IngestionRunResult, PostingError, RunStatusName
from app.schemas.canonical import CanonicalPosting


class PersistOutcome(str, enum.Enum):
    INSERTED = "inserted"
    UPDATED = "updated"
    UNCHANGED = "unchanged"


class SourcePostingSink(Protocol):
    def persist(
        self,
        *,
        identity: PostingIdentity,
        posting: CanonicalPosting,
        raw_payload: dict[str, Any],
        content_hash: str,
        run_id: uuid.UUID,
    ) -> PersistOutcome: ...


class FilteredPostingSink(Protocol):
    def record(
        self,
        *,
        identity: PostingIdentity,
        posting: CanonicalPosting,
        verdict: RelevanceVerdict,
        raw_payload: dict[str, Any],
    ) -> None: ...


class RunStore(Protocol):
    def source_lock(self, source_slug: str) -> AbstractContextManager[bool]:
        """A per-source advisory lock. The bool says whether it was acquired;
        a run that doesn't get it finishes immediately as `skipped`."""
        ...

    def start(self, *, source_slug: str, trigger: str) -> uuid.UUID: ...

    def record_error(self, run_id: uuid.UUID, error: PostingError) -> None: ...

    def finish(
        self,
        run_id: uuid.UUID,
        *,
        status: RunStatusName,
        stats: dict[str, int],
        error_summary: str | None,
    ) -> None: ...


__all__ = [
    "FilteredPostingSink",
    "IngestionRunResult",
    "PersistOutcome",
    "RunStore",
    "SourcePostingSink",
]
