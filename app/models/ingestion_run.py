from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import ForeignKey, Index, SmallInteger, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import TIMESTAMP, Uuid

from app.db.base import Base, CreatedAtMixin
from app.models.enums import RunStatus, RunTrigger, enum_check


class IngestionRun(Base, CreatedAtMixin):
    """One scan of one source. `stats` holds the counts
    (fetched / matched / inserted / updated / unchanged / filtered_out / failed).
    """

    __tablename__ = "ingestion_runs"
    __table_args__ = (
        enum_check("status", RunStatus, name="run_status"),
        enum_check("trigger", RunTrigger, name="run_trigger"),
        Index("ix_ingestion_runs_source_id_started_at", "source_id", "started_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    source_id: Mapped[int] = mapped_column(
        SmallInteger, ForeignKey("sources.id", ondelete="RESTRICT"), nullable=False
    )
    trigger: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    started_at: Mapped[dt.datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
    finished_at: Mapped[dt.datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    stats: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
