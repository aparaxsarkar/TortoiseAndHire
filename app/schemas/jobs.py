"""Query DTOs for the job store.

`JobFilters` is the search input (the API builds it from query params);
`JobSummary` / `JobSearchResult` are the outputs. No SQLAlchemy here - the
service maps ORM rows into these.
"""

from __future__ import annotations

import datetime as dt
import uuid

from pydantic import BaseModel, Field


class JobFilters(BaseModel):
    q: str | None = None  # case-insensitive substring of the title
    company: str | None = None  # case-insensitive substring of the company name
    source: str | None = None  # only jobs seen from this source slug
    remote: bool | None = None
    status: str | None = None  # jobs.status: open | closed | unknown
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class JobPostingRef(BaseModel):
    source: str
    url: str


class JobSummary(BaseModel):
    id: uuid.UUID
    title: str
    company_name: str
    location_raw: str | None = None
    remote: bool | None = None
    employment_type: str | None = None
    department: str | None = None
    posted_at: dt.datetime | None = None
    first_seen_at: dt.datetime
    last_seen_at: dt.datetime
    status: str
    postings: list[JobPostingRef] = Field(default_factory=list)


class JobSearchResult(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[JobSummary]
