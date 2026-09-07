from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Company


class CompanyRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_or_create(
        self, *, normalized_name: str, name: str, domain: str | None = None
    ) -> Company:
        stmt = select(Company).where(Company.normalized_name == normalized_name)

        existing = self.session.execute(stmt).scalar_one_or_none()
        if existing is not None:
            return existing

        company = Company(normalized_name=normalized_name, name=name, domain=domain)
        self.session.add(company)
        try:
            # SAVEPOINT: a lost race rolls back to here, not the caller's txn.
            with self.session.begin_nested():
                self.session.flush()
        except IntegrityError:
            return self.session.execute(stmt).scalar_one()
        return company
