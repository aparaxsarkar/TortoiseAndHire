from __future__ import annotations

from sqlalchemy import SmallInteger, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin


class Source(Base, CreatedAtMixin):
    """The fixed set of ingestion sources (greenhouse, lever, ashby, workday).

    Seeded by scripts/seed_sources.py; `id` is a stable smallint used as the
    first half of every dedup key.
    """

    __tablename__ = "sources"
    __table_args__ = (UniqueConstraint("slug", name="uq_sources_slug"),)

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
