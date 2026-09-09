"""`ApplicationService` against a real database."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.orm import Session

from app.models import Company, Job
from app.schemas.applications import ApplicationPatch
from app.services.applications import ApplicationNotFound, ApplicationService
from tests.integration.conftest import SessionFactory


def _seed_job(session: Session) -> uuid.UUID:
    company = Company(name="Acme", normalized_name=f"acme-{uuid.uuid4()}")
    session.add(company)
    session.flush()
    job = Job(company_id=company.id, title="ML Engineer", normalized_title="ml engineer")
    session.add(job)
    session.flush()
    return job.id


def test_first_patch_creates_at_revision_one(
    db_session: Session, session_factory: SessionFactory
) -> None:
    job_id = _seed_job(db_session)
    svc = ApplicationService(session_factory=session_factory)

    view = svc.patch(job_id, ApplicationPatch(applied=True, notes="strong match"))

    assert view.revision == 1
    assert view.applied is True
    assert view.notes == "strong match"
    assert view.updated_via == "api"
    assert view.applied_at is not None  # auto-stamped


def test_subsequent_patches_bump_the_revision(
    db_session: Session, session_factory: SessionFactory
) -> None:
    job_id = _seed_job(db_session)
    svc = ApplicationService(session_factory=session_factory)

    svc.patch(job_id, ApplicationPatch(applied=True))
    v2 = svc.patch(job_id, ApplicationPatch(outcome="screen"))
    v3 = svc.patch(job_id, ApplicationPatch(notes="phone screen booked"))

    assert (v2.revision, v3.revision) == (2, 3)
    assert v3.outcome == "screen"


def test_a_no_op_patch_does_not_bump_the_revision(
    db_session: Session, session_factory: SessionFactory
) -> None:
    job_id = _seed_job(db_session)
    svc = ApplicationService(session_factory=session_factory)

    svc.patch(job_id, ApplicationPatch(outcome="screen"))
    again = svc.patch(job_id, ApplicationPatch(outcome="screen"))

    assert again.revision == 1


def test_get_without_a_record_raises_not_found(
    db_session: Session, session_factory: SessionFactory
) -> None:
    job_id = _seed_job(db_session)
    with pytest.raises(ApplicationNotFound):
        ApplicationService(session_factory=session_factory).get(job_id)


def test_patch_on_an_unknown_job_raises_not_found(
    db_session: Session, session_factory: SessionFactory
) -> None:
    with pytest.raises(ApplicationNotFound):
        ApplicationService(session_factory=session_factory).patch(
            uuid.uuid4(), ApplicationPatch(applied=True)
        )


def test_clearing_notes_to_null_is_applied(
    db_session: Session, session_factory: SessionFactory
) -> None:
    job_id = _seed_job(db_session)
    svc = ApplicationService(session_factory=session_factory)
    svc.patch(job_id, ApplicationPatch(notes="draft"))

    cleared = svc.patch(job_id, ApplicationPatch.model_validate({"notes": None}))
    assert cleared.notes is None
    assert cleared.revision == 2
