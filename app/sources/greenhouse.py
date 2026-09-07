"""Greenhouse job-board adapter.

Public, no auth: `boards-api.greenhouse.io/v1/boards/{token}` for the company
name, `.../jobs?content=true` for the postings (HTML-entity-encoded `content`).
`token` is the board slug in `SourceQuery.targets`.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import AsyncIterator
from html import unescape
from typing import ClassVar

from app.core.rate_limit import TokenBucket
from app.schemas.canonical import CanonicalPosting, RawPosting
from app.sources._html import html_to_text
from app.sources.base import BaseSource, SourceQuery
from app.sources.errors import SourcePayloadError
from app.sources.http import HttpClient

_BASE = "https://boards-api.greenhouse.io/v1/boards"


def _is_remote(location: str | None) -> bool | None:
    if location and "remote" in location.lower():
        return True
    return None


def _parse_dt(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    try:
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


class GreenhouseSource(BaseSource):
    slug: ClassVar[str] = "greenhouse"

    def _make_http(self) -> HttpClient:
        return HttpClient(rate_limit=TokenBucket(rate=5.0, capacity=10.0))

    async def fetch(self, query: SourceQuery) -> AsyncIterator[RawPosting]:
        for token in query.targets:
            board = await self._http.get_json(f"{_BASE}/{token}")
            company_name = board.get("name") or token
            jobs = await self._http.get_json(f"{_BASE}/{token}/jobs", params={"content": "true"})
            for job in jobs.get("jobs", []):
                yield RawPosting(
                    source_slug=self.slug,
                    fetched_at=dt.datetime.now(tz=dt.UTC),
                    source_url=job.get("absolute_url") or "",
                    payload={**job, "_board_token": token, "_company_name": company_name},
                )

    def parse(self, raw: RawPosting) -> CanonicalPosting:
        p = raw.payload
        job_id = p.get("id")
        url = p.get("absolute_url")
        if job_id is None or not url:
            raise SourcePayloadError(f"greenhouse job missing id/url: {p.get('title')!r}")

        location = (p.get("location") or {}).get("name")
        departments = p.get("departments") or []
        content = p.get("content")

        return CanonicalPosting(
            source_slug=self.slug,
            source_job_id=str(job_id),
            url=url,
            company_name=p.get("_company_name") or p.get("_board_token") or "",
            title=p.get("title") or "",
            location_raw=location,
            remote=_is_remote(location),
            department=departments[0]["name"] if departments else None,
            description_html=unescape(content) if content else None,
            description_text=html_to_text(content),
            posted_at=_parse_dt(p.get("updated_at")),
            source_metadata={
                "greenhouse_internal_job_id": p.get("internal_job_id"),
                "requisition_id": p.get("requisition_id"),
                "offices": [o.get("name") for o in (p.get("offices") or [])],
            },
        )
