from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import Boolean, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import TIMESTAMP, Uuid

from app.db.base import Base, CreatedAtMixin


class ApplicationImportRun(Base, CreatedAtMixin):
    """One Excel import - dry-run *and* commit (ADR-0010). Standalone: it
    references job ids inside `report`, but has no FK, so pruning it never
    cascades anywhere.
    """

    __tablename__ = "application_import_runs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    uploaded_at: Mapped[dt.datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
    committed: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    stats: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    report: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, server_default="[]")
