from __future__ import annotations

import enum
import uuid
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models import Source, SourcePosting


class UpsertOutcome(str, enum.Enum):
    INSERTED = "inserted"
    UPDATED = "updated"
    UNCHANGED = "unchanged"


class SourcePostingRepository:
    """Writes the idempotency-anchored `source_postings` table (ADR-0002).

    `upsert` is `INSERT ... ON CONFLICT (source_id, dedup_key) DO UPDATE`. Insert
    vs. update is read back from the `xmax = 0` system-column trick; unchanged
    vs. updated is decided by comparing the prior `content_hash`.
    """

    def __init__(self, session: Session) -> None:
        self.session = session

    def content_hash_for(self, *, source_id: int, dedup_key: str) -> str | None:
        return self.session.execute(
            select(SourcePosting.content_hash).where(
                SourcePosting.source_id == source_id,
                SourcePosting.dedup_key == dedup_key,
            )
        ).scalar_one_or_none()

    def job_id_for(self, *, source_id: int, dedup_key: str) -> uuid.UUID | None:
        """The canonical job this posting already resolves to, if it's been seen."""
        return self.session.execute(
            select(SourcePosting.job_id).where(
                SourcePosting.source_id == source_id,
                SourcePosting.dedup_key == dedup_key,
            )
        ).scalar_one_or_none()

    def list_for_job(self, job_id: uuid.UUID) -> list[SourcePosting]:
        """Every posting linked to this job, ordered by source slug - the same
        order `JobRepository.source_links_for` uses, so `[0]` here matches
        what the Excel export showed as *the* URL (ADR-0013)."""
        return list(
            self.session.execute(
                select(SourcePosting)
                .join(Source, Source.id == SourcePosting.source_id)
                .where(SourcePosting.job_id == job_id)
                .order_by(Source.slug)
            ).scalars()
        )

    def upsert(
        self,
        *,
        source_id: int,
        job_id: uuid.UUID,
        source_job_id: str | None,
        canonical_url: str,
        dedup_key: str,
        raw_payload: dict[str, Any],
        content_hash: str,
        run_id: uuid.UUID | None = None,
    ) -> UpsertOutcome:
        prior_hash = self.content_hash_for(source_id=source_id, dedup_key=dedup_key)

        mutable = {
            "job_id": job_id,
            "source_job_id": source_job_id,
            "canonical_url": canonical_url,
            "raw_payload": raw_payload,
            "content_hash": content_hash,
            "last_run_id": run_id,
        }
        stmt = (
            pg_insert(SourcePosting)
            .values({"source_id": source_id, "dedup_key": dedup_key, **mutable})
            .on_conflict_do_update(
                index_elements=["source_id", "dedup_key"],
                set_={**mutable, "last_ingested_at": func.now()},
            )
            .returning(text("(xmax = 0) AS inserted"))
        )
        inserted = bool(self.session.execute(stmt).scalar_one())

        if inserted:
            return UpsertOutcome.INSERTED
        return UpsertOutcome.UNCHANGED if prior_hash == content_hash else UpsertOutcome.UPDATED
