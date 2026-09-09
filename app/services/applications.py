"""The write side of my private application tracking (ADR-0011).

`write_application` is the one place a row is created or mutated - the API PATCH
and the Excel import both go through it, so "bump `revision`, stamp
`updated_via`, auto-stamp `applied_at`" can't drift between the two paths.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Callable
from contextlib import AbstractContextManager

from sqlalchemy.orm import Session

from app.core.errors import TortoiseError
from app.db.repositories.applications import ApplicationRepository
from app.db.repositories.jobs import JobRepository
from app.db.session import session_scope
from app.models import Application
from app.models.enums import UpdatedVia
from app.schemas.applications import ApplicationPatch, ApplicationView

SessionFactory = Callable[[], AbstractContextManager[Session]]


class ApplicationNotFound(TortoiseError):
    http_status = 404
    http_title = "Not Found"


def _view(app: Application) -> ApplicationView:
    return ApplicationView(
        job_id=app.job_id,
        applied=app.applied,
        applied_at=app.applied_at,
        networking=app.networking,
        networking_notes=app.networking_notes,
        outcome=app.outcome,
        application_url=app.application_url,
        notes=app.notes,
        revision=app.revision,
        updated_via=app.updated_via,
        updated_at=app.updated_at,
    )


def write_application(
    session: Session, job_id: uuid.UUID, patch: ApplicationPatch, *, via: str
) -> tuple[Application, bool]:
    """Create or update the row for `job_id` from the *set* fields of `patch`.
    Returns `(application, changed)`. A brand-new row lands at `revision = 1`;
    each later change bumps it."""
    fields = patch.model_dump(exclude_unset=True)
    repo = ApplicationRepository(session)
    app = repo.get_by_job_id(job_id)

    if app is None:
        app = Application(job_id=job_id, updated_via=via)
        for name, value in fields.items():
            setattr(app, name, value)
        if app.applied and app.applied_at is None:
            app.applied_at = dt.datetime.now(dt.UTC)
        repo.add(app)
        return app, True

    changed = False
    for name, value in fields.items():
        if getattr(app, name) != value:
            setattr(app, name, value)
            changed = True
    if changed:
        if app.applied and app.applied_at is None and "applied_at" not in fields:
            app.applied_at = dt.datetime.now(dt.UTC)
        app.revision += 1
        app.updated_via = via
        session.flush()
    return app, changed


class ApplicationService:
    def __init__(self, *, session_factory: SessionFactory = session_scope) -> None:
        self._session_factory = session_factory

    def get(self, job_id: uuid.UUID) -> ApplicationView:
        with self._session_factory() as session:
            app = ApplicationRepository(session).get_by_job_id(job_id)
            if app is None:
                raise ApplicationNotFound(
                    f"no application record for job {job_id} yet - PATCH to create one"
                )
            return _view(app)

    def patch(self, job_id: uuid.UUID, patch: ApplicationPatch) -> ApplicationView:
        with self._session_factory() as session:
            if JobRepository(session).get(job_id) is None:
                raise ApplicationNotFound(f"no job {job_id}")
            app, _ = write_application(session, job_id, patch, via=UpdatedVia.API.value)
            return _view(app)
