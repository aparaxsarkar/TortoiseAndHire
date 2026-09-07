"""Lever postings adapter.

Public, no auth: `api.lever.co/v0/postings/{account}?mode=json` returns a JSON
array. `account` is the slug in `SourceQuery.targets`. Lever gives us plain-text
descriptions directly (`descriptionPlain`), which is nice.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import AsyncIterator
from typing import ClassVar

from app.core.rate_limit import TokenBucket
from app.schemas.canonical import CanonicalPosting, RawPosting
from app.sources._html import html_to_text
from app.sources.base import BaseSource, SourceQuery
from app.sources.errors import SourcePayloadError
from app.sources.http import HttpClient

_BASE = "https://api.lever.co/v0/postings"

_WORKPLACE_REMOTE = {"remote": True, "on-site": False}


def _parse_ms(value: object) -> dt.datetime | None:
    if not isinstance(value, (int, float)):
        return None
    try:
        return dt.datetime.fromtimestamp(value / 1000, tz=dt.UTC)
    except (OverflowError, OSError, ValueError):
        return None


class LeverSource(BaseSource):
    slug: ClassVar[str] = "lever"

    def _make_http(self) -> HttpClient:
        return HttpClient(rate_limit=TokenBucket(rate=5.0, capacity=10.0))

    async def fetch(self, query: SourceQuery) -> AsyncIterator[RawPosting]:
        for account in query.targets:
            postings = await self._http.get_json(f"{_BASE}/{account}", params={"mode": "json"})
            for posting in postings:
                yield RawPosting(
                    source_slug=self.slug,
                    fetched_at=dt.datetime.now(tz=dt.UTC),
                    source_url=posting.get("hostedUrl") or posting.get("applyUrl") or "",
                    payload={**posting, "_account": account},
                )

    def parse(self, raw: RawPosting) -> CanonicalPosting:
        p = raw.payload
        posting_id = p.get("id")
        url = p.get("hostedUrl") or p.get("applyUrl")
        if not posting_id or not url:
            raise SourcePayloadError(f"lever posting missing id/url: {p.get('text')!r}")

        cats = p.get("categories") or {}
        description_html = (
            " ".join(part for part in (p.get("description"), p.get("additional")) if part) or None
        )
        description_text = "\n\n".join(
            part for part in (p.get("descriptionPlain"), p.get("additionalPlain")) if part
        ) or html_to_text(description_html)

        return CanonicalPosting(
            source_slug=self.slug,
            source_job_id=str(posting_id),
            url=url,
            company_name=str(p.get("_account") or "").replace("-", " ").title(),
            title=p.get("text") or "",
            location_raw=cats.get("location"),
            department=cats.get("department") or cats.get("team"),
            employment_type=cats.get("commitment"),
            remote=_WORKPLACE_REMOTE.get(str(p.get("workplaceType") or "").lower()),
            description_html=description_html,
            description_text=description_text,
            posted_at=_parse_ms(p.get("createdAt")),
            source_metadata={
                "lever_account": p.get("_account"),
                "categories": cats,
                "lists": [entry.get("text") for entry in (p.get("lists") or [])],
            },
        )
