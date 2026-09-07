from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Source


class SourceRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_slug(self, slug: str) -> Source | None:
        return self.session.execute(select(Source).where(Source.slug == slug)).scalar_one_or_none()

    def list_all(self) -> list[Source]:
        return list(self.session.execute(select(Source).order_by(Source.id)).scalars())
