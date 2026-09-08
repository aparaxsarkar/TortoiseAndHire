"""Ingestion in the services layer: the ORM-backed ports, plus the service that
composes them into a run.

`RepositorySourcePostingSink` / `RepositoryFilteredPostingSink` / `RepositoryRunStore`
are the ORM half of the persistence seam - `app/ingestion/` defines the ports and
never imports a session, these bind them to real repositories. Per-posting
isolation is a SAVEPOINT (`session.begin_nested()`); the per-source advisory lock
is `pg_try_advisory_xact_lock`, released when the surrounding transaction ends.

`IngestionService` is the entry point the API, the CLI, and the scheduled job all
call: resolve the adapter, open one transaction, wire the sinks, run, map the
result to a DTO.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import uuid
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import AbstractContextManager, contextmanager
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import TortoiseError
from app.core.logging import get_logger
from app.db.repositories import (
    CompanyRepository,
    FilteredPostingRepository,
    IngestionRunRepository,
    JobRepository,
    SourcePostingRepository,
    SourceRepository,
    UpsertOutcome,
)
from app.db.session import session_scope
from app.deduplication.identity import PostingIdentity
from app.discovery.rules import RelevanceVerdict
from app.discovery.ruleset import Ruleset, load_ruleset
from app.ingestion.ports import PersistOutcome
from app.ingestion.results import IngestionRunResult, PostingError, RunStatusName
from app.ingestion.runner import IngestionRunner
from app.models import IngestionError, IngestionRun, Job, Source
from app.models.enums import RunStatus, RunTrigger
from app.schemas.canonical import CanonicalPosting
from app.schemas.ingestion import IngestionReport, IngestionRunSummary, SourceRunResult
from app.sources.base import JobSource, SourceQuery
from app.sources.registry import get_source

log = get_logger("services.ingestion")

SessionFactory = Callable[[], AbstractContextManager[Session]]
SourceFactory = Callable[[str], JobSource]

#: trigger value for a run kicked off through the HTTP API (re-exported so
#: `app/api/` doesn't have to import `app/models/`).
TRIGGER_MANUAL_API = RunTrigger.MANUAL_API.value

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


class IngestionSetupError(TortoiseError):
    """The run can't start: the source isn't seeded, or config is missing."""

    http_status = 409
    http_title = "Conflict"


def _to_dto(result: IngestionRunResult) -> SourceRunResult:
    return SourceRunResult(
        source=result.source_slug,
        status=result.status,
        run_id=result.run_id,
        error_summary=result.error_summary,
        **result.as_stats(),
    )


class IngestionService:
    """Composes a run: adapter + ruleset + one transaction + the repository sinks.

    One call == one source == one transaction. `session_scope()` commits a
    finished run (including a `partial` one) and rolls back only if the runner
    itself raises. The advisory lock lives and dies with that transaction.
    """

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        session_factory: SessionFactory = session_scope,
        source_factory: SourceFactory = get_source,
        ruleset: Ruleset | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._session_factory = session_factory
        self._source_factory = source_factory
        self._ruleset = ruleset or load_ruleset(self._settings.discovery_ruleset_path)

    async def run_source(
        self,
        slug: str,
        *,
        targets: Sequence[str],
        trigger: str = RunTrigger.SCHEDULED.value,
    ) -> SourceRunResult:
        source = self._source_factory(slug)  # raises SourceError for an unknown slug
        try:
            with self._session_factory() as session:
                source_row = SourceRepository(session).get_by_slug(slug)
                if source_row is None:
                    raise IngestionSetupError(
                        f"source {slug!r} has no row in `sources` - run scripts/seed_sources.py"
                    )
                runner = IngestionRunner(
                    source=source,
                    ruleset=self._ruleset,
                    posting_sink=RepositorySourcePostingSink(session, source_id=source_row.id),
                    filtered_sink=RepositoryFilteredPostingSink(session, source_id=source_row.id),
                    run_store=RepositoryRunStore(session),
                    trigger=trigger,
                )
                result = await runner.run(SourceQuery(targets=list(targets)))
            return _to_dto(result)
        finally:
            await source.aclose()

    async def run_all(
        self,
        *,
        plan: Mapping[str, Sequence[str]],
        trigger: str = RunTrigger.SCHEDULED.value,
    ) -> IngestionReport:
        """Run every source in `plan` ({slug: targets}). One source failing
        outright doesn't stop the others - it becomes a `failed` result."""
        results: list[SourceRunResult] = []
        for slug, targets in plan.items():
            try:
                results.append(await self.run_source(slug, targets=targets, trigger=trigger))
            except Exception as exc:
                log.exception("ingestion.service.source_failed", source=slug)
                results.append(
                    SourceRunResult(
                        source=slug,
                        status="failed",
                        error_summary=f"{type(exc).__name__}: {exc}",
                    )
                )
        return IngestionReport(results=results)

    def recent_runs(self, *, limit: int = 20) -> list[IngestionRunSummary]:
        with self._session_factory() as session:
            rows = IngestionRunRepository(session).list_recent(limit=limit)
            return [_run_summary(run, slug) for run, slug in rows]

    def get_run(self, run_id: uuid.UUID) -> IngestionRunSummary | None:
        with self._session_factory() as session:
            found = IngestionRunRepository(session).get(run_id)
            return _run_summary(found[0], found[1]) if found is not None else None


def _run_summary(run: IngestionRun, source_slug: str) -> IngestionRunSummary:
    return IngestionRunSummary(
        id=run.id,
        source=source_slug,
        trigger=run.trigger,
        status=run.status,
        started_at=run.started_at,
        finished_at=run.finished_at,
        stats={k: int(v) for k, v in run.stats.items()},
        error_summary=run.error_summary,
    )
