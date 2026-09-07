from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.db.base import Base, CreatedAtMixin
from app.models.enums import IngestionStage, enum_check


class IngestionError(Base, CreatedAtMixin):
    """One skipped posting during a run. Belongs to its run: `ON DELETE CASCADE`
    (deleting a run takes its error rows with it - the one intentional cascade).
    """

    __tablename__ = "ingestion_errors"
    __table_args__ = (
        enum_check("stage", IngestionStage, name="ingestion_stage"),
        Index("ix_ingestion_errors_run_id", "run_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("ingestion_runs.id", ondelete="CASCADE"), nullable=False
    )
    stage: Mapped[str] = mapped_column(Text, nullable=False)
    source_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_type: Mapped[str] = mapped_column(Text, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    payload_excerpt: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
