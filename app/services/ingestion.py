"""Repository-backed implementations of the ingestion ports.

This is the ORM half of the persistence seam: `app/ingestion/` defines the ports
and never imports a session, these classes bind them to real repositories.

Per-posting isolation is a SAVEPOINT (`session.begin_nested()`) around each
posting's writes, so one bad row rolls back to just before itself and the run
carries on. The per-source advisory lock is `pg_try_advisory_xact_lock`, which
releases automatically when the surrounding transaction ends.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.db.repositories import (
    CompanyRepository,
    FilteredPostingRepository,
    JobRepository,
    SourcePostingRepository,
    UpsertOutcome,
)
from app.deduplication.identity import PostingIdentity
from app.discovery.rules import RelevanceVerdict
from app.ingestion.ports import PersistOutcome
from app.ingestion.results import PostingError, RunStatusName
from app.models import IngestionError, IngestionRun, Job, Source
from app.models.enums import RunStatus
from app.schemas.canonical import CanonicalPosting

log = get_logger("services.ingestion")

_OUTCOME_MAP = {
    UpsertOutcome.INSERTED: PersistOutcome.INSERTED,
    UpsertOutcome.UPDATED: PersistOutcome.UPDATED,
    UpsertOutcome.UNCHANGED: PersistOutcome.UNCHANGED,
}


def normalize_name(value: str) -> str:
    """Whitespace-collapsed, lower-cased. The match key for companies and the
    stored `normalized_title` on jobs. A richer normalizer can come later."""
    return " ".join(value.split()).lower()


def _advisory_key(source_slug: str) -> int:
    digest = hashlib.blake2b(source_slug.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "big", signed=True)


def _job_columns(posting: CanonicalPosting) -> dict[str, Any]:
    return {
        "title": posting.title,
        "normalized_title": normalize_name(posting.title),
        "location_raw": posting.location_raw,
        "location_city": posting.location_city,
        "location_region": posting.location_region,
        "location_country": posting.location_country,
        "remote": posting.remote,
        "employment_type": posting.employment_type,
        "department": posting.department,
        "description_text": posting.description_text,
        "description_html": posting.description_html,
        "posted_at": posting.posted_at,
        "last_seen_at": dt.datetime.now(dt.UTC),
    }


class RepositorySourcePostingSink:
    """Writes `companies` + `jobs` + `source_postings` for one source."""

    def __init__(self, session: Session, *, source_id: int) -> None:
        self.session = session
        self.source_id = source_id
        self._companies = CompanyRepository(session)
        self._jobs = JobRepository(session)
        self._postings = SourcePostingRepository(session)

    def persist(
        self,
        *,
        identity: PostingIdentity,
        posting: CanonicalPosting,
        raw_payload: dict[str, Any],
        content_hash: str,
        run_id: uuid.UUID,
    ) -> PersistOutcome:
        with self.session.begin_nested():
            company = self._companies.get_or_create(
                normalized_name=normalize_name(posting.company_name),
                name=posting.company_name,
                domain=posting.company_domain,
            )

            prior_hash = self._postings.content_hash_for(
                source_id=self.source_id, dedup_key=identity.dedup_key
            )
            job_id = self._postings.job_id_for(
                source_id=self.source_id, dedup_key=identity.dedup_key
            )

            if job_id is None:
                new_job = Job(company_id=company.id, **_job_columns(posting))
                self._jobs.add(new_job)
                job_id = new_job.id
            elif prior_hash != content_hash:
                existing = self._jobs.get(job_id)
                if existing is not None:
                    for column, value in _job_columns(posting).items():
                        setattr(existing, column, value)
                    self.session.flush()

            outcome = self._postings.upsert(
                source_id=self.source_id,
                job_id=job_id,
                source_job_id=identity.source_job_id,
                canonical_url=identity.canonical_url,
                dedup_key=identity.dedup_key,
                raw_payload=raw_payload,
                content_hash=content_hash,
                run_id=run_id,
            )
        return _OUTCOME_MAP[outcome]


class RepositoryFilteredPostingSink:
    """Writes the reject ledger for one source. Never touches `jobs`."""

    def __init__(self, session: Session, *, source_id: int) -> None:
        self.session = session
        self.source_id = source_id
        self._filtered = FilteredPostingRepository(session)

    def record(
        self,
        *,
        identity: PostingIdentity,
        posting: CanonicalPosting,
        verdict: RelevanceVerdict,
        raw_payload: dict[str, Any],
    ) -> None:
        with self.session.begin_nested():
            self._filtered.upsert(
                source_id=self.source_id,
                source_job_id=identity.source_job_id,
                canonical_url=identity.canonical_url,
                dedup_key=identity.dedup_key,
                title=posting.title or None,
                company_name=posting.company_name or None,
                reasons=verdict.reasons,
                ruleset_version=verdict.ruleset_version,
                raw_payload=raw_payload,
            )


class RepositoryRunStore:
    """`ingestion_runs` / `ingestion_errors` writes + the per-source advisory lock."""

    def __init__(self, session: Session) -> None:
        self.session = session

    @contextmanager
    def source_lock(self, source_slug: str) -> Iterator[bool]:
        acquired = bool(
            self.session.execute(
                select(func.pg_try_advisory_xact_lock(_advisory_key(source_slug)))
            ).scalar_one()
        )
        # A transaction-scoped lock: nothing to release here - it drops when the
        # surrounding session's transaction commits or rolls back.
        yield acquired

    def start(self, *, source_slug: str, trigger: str) -> uuid.UUID:
        source_id = self.session.execute(
            select(Source.id).where(Source.slug == source_slug)
        ).scalar_one()
        run = IngestionRun(source_id=source_id, trigger=trigger, status=RunStatus.RUNNING.value)
        self.session.add(run)
        self.session.flush()
        return run.id

    def record_error(self, run_id: uuid.UUID, error: PostingError) -> None:
        self.session.add(
            IngestionError(
                run_id=run_id,
                stage=error.stage,
                source_ref=error.source_ref,
                error_type=error.error_type,
                message=error.message[:2000],
            )
        )
        self.session.flush()

    def finish(
        self,
        run_id: uuid.UUID,
        *,
        status: RunStatusName,
        stats: dict[str, int],
        error_summary: str | None,
    ) -> None:
        run = self.session.get(IngestionRun, run_id)
        if run is None:  # pragma: no cover - the run row is created in start()
            return
        run.status = status
        run.stats = stats
        run.error_summary = error_summary
        run.finished_at = dt.datetime.now(dt.UTC)
        self.session.flush()
