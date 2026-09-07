"""The adapter contract.

A source adapter fetches a `RawPosting` and parses it into a `CanonicalPosting`
- the single normalised shape everything downstream (deduplication, discovery,
persistence) works with. Nothing here touches the database or SQLAlchemy.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from pydantic import BaseModel, Field


class RawPosting(BaseModel):
    """What an adapter fetched, before parsing."""

    source_slug: str
    fetched_at: dt.datetime
    source_url: str
    payload: dict[str, Any]


class CanonicalPosting(BaseModel):
    """The normalised posting. The only object that leaves `app/sources/`."""

    source_slug: str
    source_job_id: str | None = None
    url: str
    company_name: str
    company_domain: str | None = None
    title: str
    location_raw: str | None = None
    location_city: str | None = None
    location_region: str | None = None
    location_country: str | None = None
    remote: bool | None = None
    employment_type: str | None = None
    department: str | None = None
    description_text: str | None = None
    description_html: str | None = None
    posted_at: dt.datetime | None = None
    compensation_raw: str | None = None
    source_metadata: dict[str, Any] = Field(default_factory=dict)
