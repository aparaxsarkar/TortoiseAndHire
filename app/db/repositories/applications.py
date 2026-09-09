from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Application


class ApplicationRepository:
    """The *only* writer of the `applications` table (ADR-0011). Never wired
    into the ingestion path."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_job_id(self, job_id: uuid.UUID) -> Application | None:
        return self.session.execute(
            select(Application).where(Application.job_id == job_id)
        ).scalar_one_or_none()

    def add(self, application: Application) -> Application:
        self.session.add(application)
        self.session.flush()
        return application

    def by_job_id(self) -> dict[uuid.UUID, Application]:
        """Every row, keyed by `job_id` - for the Excel export/import reconcile."""
        return {app.job_id: app for app in self.session.execute(select(Application)).scalars()}
