"""Read-side service for the job store.

Owns its own short-lived transaction per call (like `IngestionService`), so the
API layer never imports `app/db`. Returns plain schema DTOs - an ORM object
never leaves this layer. Redaction of private fields for unauthenticated callers
is the API's concern, not this one; this returns the full record.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from contextlib import AbstractContextManager

from sqlalchemy.orm import Session

from app.db.repositories.jobs import JobRepository
from app.db.session import session_scope
from app.models import Job
from app.schemas.jobs import JobFilters, JobPostingRef, JobSearchResult, JobSummary

SessionFactory = Callable[[], AbstractContextManager[Session]]


def _summary(job: Job, company_name: str, links: list[tuple[str, str]]) -> JobSummary:
    return JobSummary(
        id=job.id,
        title=job.title,
        company_name=company_name,
        location_raw=job.location_raw,
        remote=job.remote,
        employment_type=job.employment_type,
        department=job.department,
        posted_at=job.posted_at,
        first_seen_at=job.first_seen_at,
        last_seen_at=job.last_seen_at,
        status=job.status,
        postings=[JobPostingRef(source=slug, url=url) for slug, url in links],
    )


class JobService:
    def __init__(self, *, session_factory: SessionFactory = session_scope) -> None:
        self._session_factory = session_factory

    def search(self, filters: JobFilters) -> JobSearchResult:
        with self._session_factory() as session:
            repo = JobRepository(session)
            pairs, total = repo.search(filters)
            links = repo.source_links_for([job.id for job, _ in pairs])
            items = [_summary(job, name, links.get(job.id, [])) for job, name in pairs]
        return JobSearchResult(total=total, limit=filters.limit, offset=filters.offset, items=items)

    def get(self, job_id: uuid.UUID) -> JobSummary | None:
        with self._session_factory() as session:
            repo = JobRepository(session)
            found = repo.get_with_company(job_id)
            if found is None:
                return None
            job, company_name = found
            links = repo.source_links_for([job.id])
            return _summary(job, company_name, links.get(job.id, []))
