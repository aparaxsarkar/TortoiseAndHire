"""Public, unauthenticated, read-only job search (ADR-0008).

`JobSummary` carries no private application/networking fields - those live on a
separate protected endpoint (day 9), never on this one.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import get_job_service, job_filters
from app.api.errors import ProblemException
from app.schemas.jobs import JobFilters, JobSearchResult, JobSummary
from app.services.jobs import JobService

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("", response_model=JobSearchResult)
def list_jobs(
    filters: Annotated[JobFilters, Depends(job_filters)],
    service: Annotated[JobService, Depends(get_job_service)],
) -> JobSearchResult:
    return service.search(filters)


@router.get("/{job_id}", response_model=JobSummary)
def get_job(
    job_id: uuid.UUID,
    service: Annotated[JobService, Depends(get_job_service)],
) -> JobSummary:
    job = service.get(job_id)
    if job is None:
        raise ProblemException(status=404, title="Not Found", detail=f"No job {job_id}")
    return job
