from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import ForeignKey, SmallInteger, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import TIMESTAMP, Uuid

from app.db.base import Base, CreatedAtMixin


class FilteredPosting(Base, CreatedAtMixin):
    """The reject ledger from the relevance filter (ADR-0009).

    Same `UNIQUE (source_id, dedup_key)` discipline as `source_postings`, but
    deliberately *no* foreign key into `jobs` - a filtered posting never becomes
    a job. `raw_payload` is kept so a newer ruleset can be replayed over it
    without re-fetching.
    """

    __tablename__ = "filtered_postings"
    __table_args__ = (
        UniqueConstraint("source_id", "dedup_key", name="uq_filtered_postings_source_id_dedup_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    source_id: Mapped[int] = mapped_column(
        SmallInteger, ForeignKey("sources.id", ondelete="RESTRICT"), nullable=False
    )
    source_job_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    canonical_url: Mapped[str] = mapped_column(Text, nullable=False)
    dedup_key: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    company_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    reasons: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    ruleset_version: Mapped[str] = mapped_column(Text, nullable=False)
    raw_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    first_seen_at: Mapped[dt.datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
    last_seen_at: Mapped[dt.datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
