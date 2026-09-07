"""Constraints that only a real database can prove (ADR-0002, ADR-0009, ADR-0011)."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import Connection, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Application, Company, Job, Source, SourcePosting


def _seed_company_and_job(session: Session) -> tuple[Company, Job]:
    company = Company(name="Acme", normalized_name=f"acme-{uuid.uuid4()}")
    session.add(company)
    session.flush()
    job = Job(company_id=company.id, title="ML Engineer", normalized_title="ml engineer")
    session.add(job)
    session.flush()
    return company, job


def test_insert_path_company_job_application(db_session: Session) -> None:
    _, job = _seed_company_and_job(db_session)
    db_session.add(Application(job_id=job.id))
    db_session.flush()
    app = db_session.query(Application).filter_by(job_id=job.id).one()
    assert app.applied is False
    assert app.networking == "none"
    assert app.outcome == "none"
    assert app.revision == 1
    assert app.updated_via == "api"


def test_dedup_key_unique_per_source(db_session: Session) -> None:
    src = Source(slug=f"gh-{uuid.uuid4()}", display_name="Greenhouse")
    db_session.add(src)
    _, job = _seed_company_and_job(db_session)
    db_session.flush()

    def make(**kw: object) -> SourcePosting:
        return SourcePosting(
            source_id=src.id,
            job_id=job.id,
            canonical_url="https://x/1",
            dedup_key="dk-1",
            raw_payload={},
            content_hash="h",
            **kw,
        )

    db_session.add(make())
    db_session.flush()
    db_session.add(make())
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_partial_unique_allows_many_null_source_job_ids(db_session: Session) -> None:
    src = Source(slug=f"gh-{uuid.uuid4()}", display_name="Greenhouse")
    db_session.add(src)
    _, job = _seed_company_and_job(db_session)
    db_session.flush()
    for i in range(3):
        db_session.add(
            SourcePosting(
                source_id=src.id,
                job_id=job.id,
                source_job_id=None,
                canonical_url=f"https://x/{i}",
                dedup_key=f"dk-null-{i}",
                raw_payload={},
                content_hash="h",
            )
        )
    db_session.flush()  # three NULLs are fine; no error


def test_partial_unique_rejects_duplicate_non_null_source_job_id(db_session: Session) -> None:
    src = Source(slug=f"gh-{uuid.uuid4()}", display_name="Greenhouse")
    db_session.add(src)
    _, job = _seed_company_and_job(db_session)
    db_session.flush()

    def make(dk: str) -> SourcePosting:
        return SourcePosting(
            source_id=src.id,
            job_id=job.id,
            source_job_id="SJ-123",
            canonical_url="https://x",
            dedup_key=dk,
            raw_payload={},
            content_hash="h",
        )

    db_session.add(make("dk-a"))
    db_session.flush()
    db_session.add(make("dk-b"))  # different dedup_key, same source_job_id
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_deleting_a_tracked_job_is_blocked(db_session: Session) -> None:
    # ADR-0011: applications.job_id -> jobs is ON DELETE RESTRICT.
    _, job = _seed_company_and_job(db_session)
    db_session.add(Application(job_id=job.id))
    db_session.flush()
    with pytest.raises(IntegrityError):
        db_session.execute(text("DELETE FROM jobs WHERE id = :id"), {"id": job.id})
        db_session.flush()


def test_schema_has_no_triggers(raw_connection: Connection) -> None:
    # ADR-0011: every write goes through application code; no hidden DB path.
    count = raw_connection.execute(
        text("SELECT count(*) FROM pg_trigger WHERE NOT tgisinternal")
    ).scalar()
    assert count == 0


def test_applications_job_fk_is_restrict_in_the_database(raw_connection: Connection) -> None:
    confdeltype = raw_connection.execute(
        text("SELECT confdeltype FROM pg_constraint WHERE conname = 'fk_applications_job_id_jobs'")
    ).scalar()
    assert confdeltype == "r"  # 'r' = RESTRICT ('c' would be CASCADE)
