from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import TIMESTAMP, Boolean, Uuid

from app.db.base import Base, TimestampMixin
from app.models.enums import (
    ApplicationOutcome,
    NetworkingStatus,
    UpdatedVia,
    enum_check,
)


class Application(Base, TimestampMixin):
    """My private application tracking. 1:1 with `jobs`.

    Write-ownership invariant (ADR-0011): only ApplicationRepository writes this
    table; ingestion never touches it. The FK to `jobs` is `ON DELETE RESTRICT`
    (never CASCADE) so a tracked job cannot be deleted out from under a record.
    Every write bumps `revision` and stamps `updated_via`.
    """

    __tablename__ = "applications"
    __table_args__ = (
        UniqueConstraint("job_id", name="uq_applications_job_id"),
        enum_check("networking", NetworkingStatus, name="networking_status"),
        enum_check("outcome", ApplicationOutcome, name="application_outcome"),
        enum_check("updated_via", UpdatedVia, name="updated_via"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("jobs.id", ondelete="RESTRICT"), nullable=False
    )
    applied: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    applied_at: Mapped[dt.datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    networking: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=NetworkingStatus.NONE.value
    )
    networking_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    outcome: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=ApplicationOutcome.NONE.value
    )
    application_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    updated_via: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=UpdatedVia.API.value
    )
