"""In-memory fakes for the three ingestion ports + a no-network JobSource.

The port design (ADR-0011) exists so the runner can be driven with these and
never touch a database.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from app.discovery.rules import RelevanceVerdict
from app.ingestion.ports import PersistOutcome
from app.ingestion.results import PostingError
from app.schemas.canonical import CanonicalPosting, RawPosting

RULESET_KW: dict[str, Any] = {
    "version": "test.2026-09-07",
    "target_functions": ["engineer", "developer"],
    "target_levels": ["junior", "new grad", "early career"],
    "exclude_title_tokens": ["senior", "staff", "principal", "lead", "manager"],
    "max_experience_years": 3,
    "include_internships": False,
    "locations": None,
}


def make_raw(
    *,
    source_slug: str = "greenhouse",
    source_url: str = "https://boards.greenhouse.io/acme/jobs/1",
    **payload: Any,
) -> RawPosting:
    body: dict[str, Any] = {
        "id": "1",
        "title": "Software Engineer",
        "company_name": "Acme",
        "url": source_url,
    }
    body.update(payload)
    return RawPosting(
        source_slug=source_slug,
        fetched_at=dt.datetime(2026, 9, 7, tzinfo=dt.UTC),
        source_url=source_url,
        payload=body,
    )


def canon_from_raw(raw: RawPosting) -> CanonicalPosting:
    p = raw.payload
    return CanonicalPosting(
        source_slug=raw.source_slug,
        source_job_id=p.get("id"),
        url=p.get("url") or raw.source_url,
        company_name=p.get("company_name", "Acme"),
        title=p.get("title", "Software Engineer"),
        description_text=p.get("description_text"),
        remote=p.get("remote"),
    )


class FakeSource:
    def __init__(
        self,
        raws: list[RawPosting] | None = None,
        *,
        slug: str = "greenhouse",
        parse_map: dict[str, CanonicalPosting | Exception] | None = None,
        fail_fetch_times: int = 0,
        fetch_exc: Exception | None = None,
    ) -> None:
        self.slug = slug
        self.raws = raws or []
        self.parse_map = parse_map or {}
        self.fail_fetch_times = fail_fetch_times
        self.fetch_exc = fetch_exc
        self.fetch_calls = 0

    async def fetch(self, query: Any) -> Any:
        self.fetch_calls += 1
        if self.fetch_calls <= self.fail_fetch_times:
            assert self.fetch_exc is not None
            raise self.fetch_exc
        for raw in self.raws:
            yield raw

    def parse(self, raw: RawPosting) -> CanonicalPosting:
        hit = self.parse_map.get(raw.source_url)
        if isinstance(hit, Exception):
            raise hit
        if hit is not None:
            return hit
        return canon_from_raw(raw)


class FakeRunStore:
    def __init__(self, *, lock_granted: bool = True) -> None:
        self.lock_granted = lock_granted
        self.run_id = uuid.uuid4()
        self.started: list[tuple[str, str]] = []
        self.finished: list[dict[str, Any]] = []
        self.errors: list[PostingError] = []

    @contextmanager
    def source_lock(self, source_slug: str) -> Iterator[bool]:
        yield self.lock_granted

    def start(self, *, source_slug: str, trigger: str) -> uuid.UUID:
        self.started.append((source_slug, trigger))
        return self.run_id

    def record_error(self, run_id: uuid.UUID, error: PostingError) -> None:
        self.errors.append(error)

    def finish(
        self, run_id: uuid.UUID, *, status: str, stats: dict[str, int], error_summary: str | None
    ) -> None:
        self.finished.append({"status": status, "stats": stats, "error_summary": error_summary})


class FakeSourcePostingSink:
    def __init__(
        self,
        *,
        outcomes: dict[str, PersistOutcome] | None = None,
        raise_on: set[str] | None = None,
    ) -> None:
        self.outcomes = outcomes or {}
        self.raise_on = raise_on or set()
        self.persisted: list[str] = []

    def persist(
        self,
        *,
        identity: Any,
        posting: CanonicalPosting,
        raw_payload: dict[str, Any],
        content_hash: str,
        run_id: uuid.UUID,
    ) -> PersistOutcome:
        if identity.dedup_key in self.raise_on:
            raise RuntimeError(f"db write failed for {identity.dedup_key}")
        self.persisted.append(identity.dedup_key)
        return self.outcomes.get(identity.dedup_key, PersistOutcome.INSERTED)


class FakeFilteredPostingSink:
    def __init__(self, *, raise_on: set[str] | None = None) -> None:
        self.raise_on = raise_on or set()
        self.recorded: list[tuple[str, list[str]]] = []

    def record(
        self,
        *,
        identity: Any,
        posting: CanonicalPosting,
        verdict: RelevanceVerdict,
        raw_payload: dict[str, Any],
    ) -> None:
        if identity.dedup_key in self.raise_on:
            raise RuntimeError(f"filtered write failed for {identity.dedup_key}")
        self.recorded.append((identity.dedup_key, verdict.reasons))
