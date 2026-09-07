"""The runner end-to-end against a real database, through the repository-backed
sinks. Proves idempotency (ADR-0002), the reject ledger (ADR-0009), and the
write-ownership invariant (ADR-0011) as a whole rather than per repository.
"""

from __future__ import annotations

import uuid

from sqlalchemy import Engine, func, select, text
from sqlalchemy.orm import Session

from app.discovery.ruleset import Ruleset
from app.ingestion.runner import IngestionRunner
from app.models import (
    Application,
    FilteredPosting,
    IngestionError,
    IngestionRun,
    Job,
    Source,
    SourcePosting,
)
from app.services.ingestion import (
    RepositoryFilteredPostingSink,
    RepositoryRunStore,
    RepositorySourcePostingSink,
)
from app.sources.base import SourceQuery
from tests.unit.ingestion.fakes import RULESET_KW, FakeSource, make_raw

RULESET = Ruleset(**RULESET_KW)
QUERY = SourceQuery(targets=["acme"])


def _seed_source(session: Session) -> Source:
    src = Source(slug=f"greenhouse-{uuid.uuid4()}", display_name="Greenhouse")
    session.add(src)
    session.flush()
    return src


def _runner(session: Session, source: FakeSource, source_id: int) -> IngestionRunner:
    return IngestionRunner(
        source=source,
        ruleset=RULESET,
        posting_sink=RepositorySourcePostingSink(session, source_id=source_id),
        filtered_sink=RepositoryFilteredPostingSink(session, source_id=source_id),
        run_store=RepositoryRunStore(session),
        trigger="cli",
        fetch_retry_backoff=0.0,
    )


def _three_postings(url_prefix: str = "https://x") -> list:
    return [
        make_raw(
            id="1",
            title="Software Engineer",
            company_name="Acme",
            source_url=f"{url_prefix}/1",
            description_text="Build things. 0-2 yrs.",
        ),
        make_raw(
            id="2",
            title="Backend Developer",
            company_name="Acme",
            source_url=f"{url_prefix}/2",
            description_text="APIs and pipelines.",
        ),
        make_raw(
            id="3",
            title="Senior Staff Engineer",
            company_name="Acme",
            source_url=f"{url_prefix}/3",
            description_text="10+ years of experience.",
        ),
    ]


async def test_full_run_persists_jobs_and_routes_the_reject(db_session: Session) -> None:
    src_row = _seed_source(db_session)
    source = FakeSource(_three_postings(), slug=src_row.slug)

    result = await _runner(db_session, source, src_row.id).run(QUERY)

    assert (result.matched, result.inserted, result.filtered_out) == (2, 2, 1)
    assert result.status == "success"

    jobs = db_session.execute(select(func.count()).select_from(Job)).scalar_one()
    postings = db_session.execute(
        select(func.count()).select_from(SourcePosting).where(SourcePosting.source_id == src_row.id)
    ).scalar_one()
    rejects = (
        db_session.execute(select(FilteredPosting).where(FilteredPosting.source_id == src_row.id))
        .scalars()
        .all()
    )
    assert (jobs, postings) == (2, 2)
    assert len(rejects) == 1
    assert "seniority_excluded" in rejects[0].reasons

    run_row = db_session.execute(
        select(IngestionRun).where(IngestionRun.source_id == src_row.id)
    ).scalar_one()
    assert run_row.status == "success"
    assert run_row.trigger == "cli"
    assert run_row.stats["inserted"] == 2
    assert run_row.stats["filtered_out"] == 1
    assert run_row.finished_at is not None


async def test_re_ingesting_identical_data_changes_nothing(db_session: Session) -> None:
    src_row = _seed_source(db_session)
    raws = _three_postings()

    first = await _runner(db_session, FakeSource(raws, slug=src_row.slug), src_row.id).run(QUERY)
    assert first.inserted == 2

    sp = db_session.execute(
        select(SourcePosting).where(
            SourcePosting.source_id == src_row.id, SourcePosting.dedup_key == "1"
        )
    ).scalar_one()
    first_ingested_at = sp.first_ingested_at

    second = await _runner(db_session, FakeSource(raws, slug=src_row.slug), src_row.id).run(QUERY)

    assert (second.inserted, second.updated, second.unchanged) == (0, 0, 2)
    assert second.status == "success"
    assert db_session.execute(select(func.count()).select_from(Job)).scalar_one() == 2
    assert (
        db_session.execute(
            select(func.count())
            .select_from(SourcePosting)
            .where(SourcePosting.source_id == src_row.id)
        ).scalar_one()
        == 2
    )
    db_session.refresh(sp)
    assert sp.first_ingested_at == first_ingested_at


async def test_a_changed_posting_is_an_update(db_session: Session) -> None:
    src_row = _seed_source(db_session)
    await _runner(db_session, FakeSource(_three_postings(), slug=src_row.slug), src_row.id).run(
        QUERY
    )

    changed = _three_postings()
    changed[0].payload["title"] = "Software Engineer II"
    changed[0].payload["description_text"] = "Now with more scope."

    result = await _runner(db_session, FakeSource(changed, slug=src_row.slug), src_row.id).run(
        QUERY
    )

    assert (result.updated, result.unchanged) == (1, 1)
    job = db_session.execute(
        select(Job)
        .join(SourcePosting, SourcePosting.job_id == Job.id)
        .where(SourcePosting.source_id == src_row.id, SourcePosting.dedup_key == "1")
    ).scalar_one()
    assert job.title == "Software Engineer II"


async def test_a_persist_failure_is_isolated_and_marks_the_run_partial(
    db_session: Session,
) -> None:
    src_row = _seed_source(db_session)

    class BoomSink(RepositorySourcePostingSink):
        def persist(self, *, identity, **kw):
            if identity.dedup_key == "2":
                raise RuntimeError("simulated db failure")
            return super().persist(identity=identity, **kw)

    runner = IngestionRunner(
        source=FakeSource(_three_postings(), slug=src_row.slug),
        ruleset=RULESET,
        posting_sink=BoomSink(db_session, source_id=src_row.id),
        filtered_sink=RepositoryFilteredPostingSink(db_session, source_id=src_row.id),
        run_store=RepositoryRunStore(db_session),
        fetch_retry_backoff=0.0,
    )
    result = await runner.run(QUERY)

    assert (result.inserted, result.failed) == (1, 1)
    assert result.status == "partial"
    err = db_session.execute(
        select(IngestionError).where(IngestionError.run_id == result.run_id)
    ).scalar_one()
    assert err.stage == "persist"
    assert err.source_ref == "2"
    # the good posting still landed
    assert db_session.execute(select(func.count()).select_from(Job)).scalar_one() == 1


async def test_ingestion_never_touches_an_applications_row(db_session: Session) -> None:
    src_row = _seed_source(db_session)
    await _runner(db_session, FakeSource(_three_postings(), slug=src_row.slug), src_row.id).run(
        QUERY
    )

    job = db_session.execute(
        select(Job)
        .join(SourcePosting, SourcePosting.job_id == Job.id)
        .where(SourcePosting.source_id == src_row.id, SourcePosting.dedup_key == "1")
    ).scalar_one()
    app = Application(job_id=job.id, applied=True, outcome="screen", notes="my private notes")
    db_session.add(app)
    db_session.flush()
    db_session.refresh(app)
    before = (app.revision, app.applied, app.outcome, app.notes, app.updated_via, app.updated_at)

    changed = _three_postings()
    changed[0].payload["title"] = "Software Engineer II"
    changed[0].payload["description_text"] = "Rewritten."
    result = await _runner(db_session, FakeSource(changed, slug=src_row.slug), src_row.id).run(
        QUERY
    )
    assert result.updated == 1

    db_session.refresh(app)
    after = (app.revision, app.applied, app.outcome, app.notes, app.updated_via, app.updated_at)
    assert before == after

    db_session.refresh(job)
    assert job.title == "Software Engineer II"  # the job did change; the application did not


async def test_run_skipped_when_the_source_lock_is_held(
    db_session: Session, migrated_engine: Engine
) -> None:
    from app.services.ingestion import _advisory_key

    src_row = _seed_source(db_session)
    db_session.flush()

    holder = migrated_engine.connect()
    try:
        with holder.begin():  # a second connection holds the per-source lock
            holder.execute(
                text("SELECT pg_advisory_xact_lock(:k)"), {"k": _advisory_key(src_row.slug)}
            )

            result = await _runner(
                db_session, FakeSource(_three_postings(), slug=src_row.slug), src_row.id
            ).run(QUERY)

            assert result.status == "skipped"
            assert result.run_id is None
            assert (
                db_session.execute(select(func.count()).select_from(IngestionRun)).scalar_one() == 0
            )
    finally:
        holder.close()
