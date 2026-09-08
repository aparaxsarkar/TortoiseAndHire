"""Read-side service for the job store.

Takes a `Session`, returns plain schema DTOs - the API layer never sees an ORM
object. Redaction of private fields for unauthenticated callers is the API's
job, not this one; this returns the full record.
"""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.db.repositories.jobs import JobRepository
from app.models import Job
from app.schemas.jobs import JobFilters, JobPostingRef, JobSearchResult, JobSummary


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
    def __init__(self, session: Session) -> None:
        self._jobs = JobRepository(session)

    def search(self, filters: JobFilters) -> JobSearchResult:
        pairs, total = self._jobs.search(filters)
        links = self._jobs.source_links_for([job.id for job, _ in pairs])
        return JobSearchResult(
            total=total,
            limit=filters.limit,
            offset=filters.offset,
            items=[_summary(job, name, links.get(job.id, [])) for job, name in pairs],
        )

    def get(self, job_id: uuid.UUID) -> JobSummary | None:
        found = self._jobs.get_with_company(job_id)
        if found is None:
            return None
        job, company_name = found
        links = self._jobs.source_links_for([job.id])
        return _summary(job, company_name, links.get(job.id, []))
