"""`IngestionRunner` - one scan of one source.

Orchestration only. It holds a `JobSource`, a `Ruleset`, and the three ports;
it owns the advisory lock, the retry-around-fetch, the relevance gate, the
per-posting failure isolation, and the run tally. It never sees a database
session - everything that persists goes through a sink.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from app.core.logging import get_logger
from app.core.retry import async_retry_policy
from app.discovery.ruleset import Ruleset
from app.ingestion.pipeline import PipelineError, prepare
from app.ingestion.ports import (
    FilteredPostingSink,
    PersistOutcome,
    RunStore,
    SourcePostingSink,
)
from app.ingestion.results import IngestionRunResult, PostingError
from app.schemas.canonical import RawPosting
from app.sources.base import JobSource, SourceQuery
from app.sources.errors import SourceError, SourceUnavailable

log = get_logger("ingestion.runner")


@dataclass
class IngestionRunner:
    source: JobSource
    ruleset: Ruleset
    posting_sink: SourcePostingSink
    filtered_sink: FilteredPostingSink
    run_store: RunStore
    trigger: str = "scheduled"
    fetch_retry_attempts: int = 3
    fetch_retry_backoff: float = 1.0

    async def run(self, query: SourceQuery) -> IngestionRunResult:
        slug = self.source.slug
        result = IngestionRunResult(source_slug=slug)

        with self.run_store.source_lock(slug) as acquired:
            if not acquired:
                result.status = "skipped"
                log.info("ingestion.run.skipped", source=slug, reason="locked")
                return result

            run_id = self.run_store.start(source_slug=slug, trigger=self.trigger)
            result.run_id = run_id
            log.info("ingestion.run.started", source=slug, run_id=str(run_id), trigger=self.trigger)

            try:
                raws = await self._fetch(query)
            except SourceError as exc:
                result.status = "failed"
                result.error_summary = f"{type(exc).__name__}: {exc}"
                self.run_store.record_error(
                    run_id, PostingError("fetch", None, type(exc).__name__, str(exc))
                )
                self.run_store.finish(
                    run_id,
                    status=result.status,
                    stats=result.as_stats(),
                    error_summary=result.error_summary,
                )
                log.warning("ingestion.run.fetch_failed", source=slug, error=str(exc))
                return result

            for raw in raws:
                self._handle(raw, run_id, result)

            result.status = "partial" if result.failed else "success"
            if result.failed:
                result.error_summary = f"{result.failed} posting(s) skipped"
            self.run_store.finish(
                run_id,
                status=result.status,
                stats=result.as_stats(),
                error_summary=result.error_summary,
            )
            log.info(
                "ingestion.run.finished", source=slug, status=result.status, **result.as_stats()
            )

        return result

    async def _fetch(self, query: SourceQuery) -> list[RawPosting]:
        async def _collect() -> list[RawPosting]:
            return [raw async for raw in self.source.fetch(query)]

        retrying = async_retry_policy(
            retry_on=SourceUnavailable,
            max_attempts=self.fetch_retry_attempts,
            initial_backoff=self.fetch_retry_backoff,
            max_backoff=8.0,
        )
        return await retrying(_collect)

    def _handle(self, raw: RawPosting, run_id: uuid.UUID, result: IngestionRunResult) -> None:
        result.fetched += 1

        try:
            prepared = prepare(raw, self.source, self.ruleset)
        except PipelineError as exc:
            self._fail(
                run_id, result, PostingError(exc.stage, exc.source_ref, exc.error_type, str(exc))
            )
            return

        identity = prepared.identity

        if not prepared.verdict.matched:
            result.filtered_out += 1
            try:
                self.filtered_sink.record(
                    identity=identity,
                    posting=prepared.posting,
                    verdict=prepared.verdict,
                    raw_payload=raw.payload,
                )
            except Exception as exc:
                self._fail(
                    run_id,
                    result,
                    PostingError("persist", identity.dedup_key, type(exc).__name__, str(exc)),
                )
            return

        result.matched += 1
        try:
            outcome = self.posting_sink.persist(
                identity=identity,
                posting=prepared.posting,
                raw_payload=raw.payload,
                content_hash=prepared.content_hash,
                run_id=run_id,
            )
        except Exception as exc:
            self._fail(
                run_id,
                result,
                PostingError("persist", identity.dedup_key, type(exc).__name__, str(exc)),
            )
            return

        if outcome is PersistOutcome.INSERTED:
            result.inserted += 1
        elif outcome is PersistOutcome.UPDATED:
            result.updated += 1
        else:
            result.unchanged += 1

    def _fail(self, run_id: uuid.UUID, result: IngestionRunResult, error: PostingError) -> None:
        result.failed += 1
        result.errors.append(error)
        self.run_store.record_error(run_id, error)
        log.warning(
            "ingestion.posting.skipped",
            source=self.source.slug,
            stage=error.stage,
            ref=error.source_ref,
            error=error.error_type,
        )
