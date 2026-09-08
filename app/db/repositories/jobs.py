from __future__ import annotations

import uuid
from collections import defaultdict
from collections.abc import Sequence

from sqlalchemy import ColumnElement, func, nullslast, select
from sqlalchemy.orm import Session

from app.models import Company, Job, Source, SourcePosting
from app.schemas.jobs import JobFilters


class JobRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, job: Job) -> Job:
        self.session.add(job)
        self.session.flush()
        return job

    def get(self, job_id: uuid.UUID) -> Job | None:
        return self.session.get(Job, job_id)

    def get_with_company(self, job_id: uuid.UUID) -> tuple[Job, str] | None:
        row = self.session.execute(
            select(Job, Company.name)
            .join(Company, Company.id == Job.company_id)
            .where(Job.id == job_id)
        ).one_or_none()
        return (row[0], row[1]) if row is not None else None

    def search(self, filters: JobFilters) -> tuple[list[tuple[Job, str]], int]:
        conds: list[ColumnElement[bool]] = []
        if filters.q:
            conds.append(Job.normalized_title.ilike(f"%{filters.q.strip()}%"))
        if filters.company:
            conds.append(Company.name.ilike(f"%{filters.company.strip()}%"))
        if filters.status:
            conds.append(Job.status == filters.status)
        if filters.remote is not None:
            conds.append(Job.remote.is_(filters.remote))
        if filters.source:
            seen_from = (
                select(SourcePosting.job_id)
                .join(Source, Source.id == SourcePosting.source_id)
                .where(Source.slug == filters.source)
            )
            conds.append(Job.id.in_(seen_from))

        total: int = self.session.execute(
            select(func.count())
            .select_from(Job)
            .join(Company, Company.id == Job.company_id)
            .where(*conds)
        ).scalar_one()

        rows = self.session.execute(
            select(Job, Company.name)
            .join(Company, Company.id == Job.company_id)
            .where(*conds)
            .order_by(nullslast(Job.posted_at.desc()), Job.first_seen_at.desc())
            .limit(filters.limit)
            .offset(filters.offset)
        ).all()
        return [(row[0], row[1]) for row in rows], total

    def source_links_for(
        self, job_ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, list[tuple[str, str]]]:
        """`{job_id: [(source_slug, canonical_url), ...]}` for the given jobs, one query."""
        if not job_ids:
            return {}
        rows = self.session.execute(
            select(SourcePosting.job_id, Source.slug, SourcePosting.canonical_url)
            .join(Source, Source.id == SourcePosting.source_id)
            .where(SourcePosting.job_id.in_(job_ids))
            .order_by(SourcePosting.job_id, Source.slug)
        ).all()
        out: dict[uuid.UUID, list[tuple[str, str]]] = defaultdict(list)
        for job_id, slug, url in rows:
            out[job_id].append((slug, url))
        return dict(out)
