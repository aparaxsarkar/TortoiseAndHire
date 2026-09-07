from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import ForeignKey, Index, SmallInteger, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import TIMESTAMP, Uuid

from app.db.base import Base, TimestampMixin


class SourcePosting(Base, TimestampMixin):
    """The idempotency anchor (ADR-0002).

    `dedup_key` is materialised on write as `coalesce(source_job_id,
    canonical_url)`. `UNIQUE (source_id, dedup_key)` is the guarantee that
    re-ingesting the same posting can only ever touch one row. The partial
    unique on `(source_id, source_job_id)` backs it up when the provider gives
    us a real id.
    """

    __tablename__ = "source_postings"
    __table_args__ = (
        UniqueConstraint("source_id", "dedup_key", name="uq_source_postings_source_id_dedup_key"),
        Index(
            "uq_source_postings_source_job_id_partial",
            "source_id",
            "source_job_id",
            unique=True,
            postgresql_where=text("source_job_id IS NOT NULL"),
        ),
        Index("ix_source_postings_job_id", "job_id"),
        Index("ix_source_postings_canonical_url", "canonical_url"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    source_id: Mapped[int] = mapped_column(
        SmallInteger, ForeignKey("sources.id", ondelete="RESTRICT"), nullable=False
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("jobs.id", ondelete="RESTRICT"), nullable=False
    )
    source_job_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    canonical_url: Mapped[str] = mapped_column(Text, nullable=False)
    dedup_key: Mapped[str] = mapped_column(Text, nullable=False)
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    first_ingested_at: Mapped[dt.datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
    last_ingested_at: Mapped[dt.datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
    last_run_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("ingestion_runs.id", ondelete="SET NULL"), nullable=True
    )
