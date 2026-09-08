from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import IngestionRun, Source


class IngestionRunRepository:
    """Read-only view of `ingestion_runs` for the API. Writes go through
    `RepositoryRunStore` during a run."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def list_recent(self, *, limit: int = 20) -> list[tuple[IngestionRun, str]]:
        rows = self.session.execute(
            select(IngestionRun, Source.slug)
            .join(Source, Source.id == IngestionRun.source_id)
            .order_by(IngestionRun.started_at.desc())
            .limit(limit)
        ).all()
        return [(row[0], row[1]) for row in rows]

    def get(self, run_id: uuid.UUID) -> tuple[IngestionRun, str] | None:
        row = self.session.execute(
            select(IngestionRun, Source.slug)
            .join(Source, Source.id == IngestionRun.source_id)
            .where(IngestionRun.id == run_id)
        ).one_or_none()
        return (row[0], row[1]) if row is not None else None
