"""Ashby job-board adapter.

Public, no auth, one call per board:
`GET https://api.ashbyhq.com/posting-api/job-board/{token}` returns
`{"apiVersion": "1", "jobs": [...]}`. `token` is the board name in
`SourceQuery.targets` (the segment after `jobs.ashbyhq.com/`). Every job has a
UUID `id`, both `descriptionHtml` and `descriptionPlain`, and a structured
`address`. The response carries no company name, so it's derived from the token
(like Lever's account slug).
"""

from __future__ import annotations

import datetime as dt
from collections.abc import AsyncIterator
from typing import Any, ClassVar

from app.core.rate_limit import TokenBucket
from app.schemas.canonical import CanonicalPosting, RawPosting
from app.sources._html import html_to_text
from app.sources.base import BaseSource, SourceQuery
from app.sources.errors import SourcePayloadError
from app.sources.http import HttpClient

_BASE = "https://api.ashbyhq.com/posting-api/job-board"


def _parse_dt(value: Any) -> dt.datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _remote(job: dict[str, Any]) -> bool | None:
    if isinstance(job.get("isRemote"), bool):
        return bool(job["isRemote"])
    workplace = str(job.get("workplaceType") or "").lower()
    if workplace == "remote":
        return True
    if workplace in ("onsite", "on-site"):
        return False
    location = str(job.get("location") or "").lower()
    return True if "remote" in location else None


def _postal(job: dict[str, Any], key: str) -> str | None:
    postal = ((job.get("address") or {}).get("postalAddress")) or {}
    value = postal.get(key)
    return value.strip() or None if isinstance(value, str) else None


class AshbySource(BaseSource):
    slug: ClassVar[str] = "ashby"

    def _make_http(self) -> HttpClient:
        return HttpClient(rate_limit=TokenBucket(rate=5.0, capacity=10.0))

    async def fetch(self, query: SourceQuery) -> AsyncIterator[RawPosting]:
        for token in query.targets:
            board = await self._http.get_json(f"{_BASE}/{token}")
            for job in board.get("jobs", []):
                yield RawPosting(
                    source_slug=self.slug,
                    fetched_at=dt.datetime.now(tz=dt.UTC),
                    source_url=job.get("jobUrl") or job.get("applyUrl") or "",
                    payload={**job, "_board": token},
                )

    def parse(self, raw: RawPosting) -> CanonicalPosting:
        p = raw.payload
        job_id = p.get("id")
        url = p.get("jobUrl") or p.get("applyUrl")
        if not job_id or not url:
            raise SourcePayloadError(f"ashby job missing id/url: {p.get('title')!r}")

        html = p.get("descriptionHtml")
        return CanonicalPosting(
            source_slug=self.slug,
            source_job_id=str(job_id),
            url=url,
            company_name=str(p.get("_board") or "").replace("-", " ").title(),
            title=p.get("title") or "",
            location_raw=p.get("location"),
            location_city=_postal(p, "addressLocality"),
            location_region=_postal(p, "addressRegion"),
            location_country=_postal(p, "addressCountry"),
            remote=_remote(p),
            employment_type=p.get("employmentType"),
            department=p.get("department") or p.get("team"),
            description_html=html,
            description_text=p.get("descriptionPlain") or html_to_text(html),
            posted_at=_parse_dt(p.get("publishedAt")),
            source_metadata={
                "ashby_board": p.get("_board"),
                "apply_url": p.get("applyUrl"),
                "workplace_type": p.get("workplaceType"),
                "team": p.get("team"),
                "is_listed": p.get("isListed"),
                "secondary_locations": [
                    loc.get("location")
                    for loc in (p.get("secondaryLocations") or [])
                    if isinstance(loc, dict)
                ],
            },
        )
