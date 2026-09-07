"""Repository behaviour that needs a real database (upsert / ON CONFLICT / get_or_create)."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.repositories import (
    CompanyRepository,
    FilteredPostingRepository,
    SourcePostingRepository,
    UpsertOutcome,
)
from app.models import Company, FilteredPosting, Job, Source, SourcePosting


def _source_and_job(session: Session) -> tuple[int, uuid.UUID]:
    src = Source(slug=f"gh-{uuid.uuid4()}", display_name="Greenhouse")
    company = Company(name="Acme", normalized_name=f"acme-{uuid.uuid4()}")
    session.add_all([src, company])
    session.flush()
    job = Job(company_id=company.id, title="MLE", normalized_title="mle")
    session.add(job)
    session.flush()
    return src.id, job.id


def test_get_or_create_creates_then_reuses(db_session: Session) -> None:
    repo = CompanyRepository(db_session)
    norm = f"acme-{uuid.uuid4()}"

    first = repo.get_or_create(normalized_name=norm, name="Acme Inc")
    db_session.flush()
    second = repo.get_or_create(normalized_name=norm, name="Acme Inc (ignored)")

    assert first.id == second.id
    count = db_session.execute(
        select(func.count()).select_from(Company).where(Company.normalized_name == norm)
    ).scalar_one()
    assert count == 1


def test_source_posting_upsert_inserted_unchanged_updated(db_session: Session) -> None:
    source_id, job_id = _source_and_job(db_session)
    repo = SourcePostingRepository(db_session)

    common = {
        "source_id": source_id,
        "job_id": job_id,
        "source_job_id": "SJ-1",
        "canonical_url": "https://x/1",
        "dedup_key": "SJ-1",
        "raw_payload": {"v": 1},
    }

    assert repo.upsert(**common, content_hash="h1") == UpsertOutcome.INSERTED
    assert repo.upsert(**common, content_hash="h1") == UpsertOutcome.UNCHANGED
    assert repo.upsert(**common, content_hash="h2") == UpsertOutcome.UPDATED

    rows = (
        db_session.execute(select(SourcePosting).where(SourcePosting.source_id == source_id))
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert rows[0].content_hash == "h2"
    assert rows[0].raw_payload == {"v": 1}


def test_source_posting_upsert_keys_on_source_plus_dedup_key(db_session: Session) -> None:
    source_id, job_id = _source_and_job(db_session)
    other_source, _ = _source_and_job(db_session)
    repo = SourcePostingRepository(db_session)

    base = {
        "job_id": job_id,
        "source_job_id": None,
        "canonical_url": "https://x/9",
        "dedup_key": "https://x/9",
        "raw_payload": {},
        "content_hash": "h",
    }
    # same dedup_key, different source -> two rows, both inserted.
    assert repo.upsert(source_id=source_id, **base) == UpsertOutcome.INSERTED
    assert repo.upsert(source_id=other_source, **base) == UpsertOutcome.INSERTED
    total = db_session.execute(select(func.count()).select_from(SourcePosting)).scalar_one()
    assert total == 2


def test_filtered_posting_upsert_is_idempotent(db_session: Session) -> None:
    source_id, _ = _source_and_job(db_session)
    repo = FilteredPostingRepository(db_session)
    key = {
        "source_id": source_id,
        "source_job_id": "SJ-9",
        "canonical_url": "https://x/9",
        "dedup_key": "SJ-9",
        "title": "Senior Something",
        "company_name": "Acme",
    }

    repo.upsert(**key, reasons=["seniority_excluded"], ruleset_version="v1")
    repo.upsert(**key, reasons=["seniority_excluded", "location_excluded"], ruleset_version="v2")

    rows = (
        db_session.execute(select(FilteredPosting).where(FilteredPosting.source_id == source_id))
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert rows[0].reasons == ["seniority_excluded", "location_excluded"]
    assert rows[0].ruleset_version == "v2"
