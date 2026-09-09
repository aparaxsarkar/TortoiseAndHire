"""Workday careers adapter.

Workday has no single universal API - every tenant differs by **shard**
(`wd1`/`wd3`/`wd5`/...) and **site** (`External`, `NVIDIAExternalCareerSite`,
`jobs`, ...). So a target is `"<tenant>:<shard>:<site>"` (or the full
`.../wday/cxs/<tenant>/<site>` URL), configured in `config/sources.yml`.

Two calls per posting:
  1. `POST {base}/jobs`  body `{"appliedFacets":{}, "limit":20, "offset":0, "searchText":""}`
     -> `{"total": N, "jobPostings": [{title, externalPath, locationsText,
     postedOn, bulletFields}]}`. `limit` must be <= 20; page by `offset`.
     `postedOn` is a localised string, not a date.
  2. `GET {base}{externalPath}` -> `{"jobPostingInfo": {id, jobDescription, location,
     additionalLocations, startDate, timeType, remoteType, ...}, "hiringOrganization": {...}}`.

A detail GET that fails is isolated: the posting is still yielded with just the
list fields, and `parse()` falls back to the req id + a built URL for identity.
"""

from __future__ import annotations

import datetime as dt
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, ClassVar

from app.core.logging import get_logger
from app.core.rate_limit import TokenBucket
from app.schemas.canonical import CanonicalPosting, RawPosting
from app.sources._html import html_to_text
from app.sources.base import BaseSource, SourceQuery
from app.sources.errors import SourceError, SourcePayloadError
from app.sources.http import HttpClient

log = get_logger("sources.workday")

_PAGE = 20  # Workday returns nothing for limit > 20
_MAX_POSTINGS = 300  # per target; a big tenant is capped (documented in config/sources.yml)
_LIST_BODY: dict[str, Any] = {"appliedFacets": {}, "limit": _PAGE, "offset": 0, "searchText": ""}
_URL_RE = re.compile(
    r"https?://(?P<tenant>[^./]+)\.(?P<shard>wd\d+)\.myworkdayjobs\.com/wday/cxs/[^/]+/(?P<site>[^/?#]+)"
)
_REQ_TAIL_RE = re.compile(r"_([A-Za-z0-9][A-Za-z0-9-]*)$")


@dataclass(frozen=True, slots=True)
class _Board:
    tenant: str
    shard: str
    site: str

    @property
    def base(self) -> str:
        return f"https://{self.tenant}.{self.shard}.myworkdayjobs.com/wday/cxs/{self.tenant}/{self.site}"

    def posting_url(self, external_path: str) -> str:
        return f"https://{self.tenant}.{self.shard}.myworkdayjobs.com/{self.site}{external_path}"


def _parse_target(target: str) -> _Board:
    text = target.strip()
    match = _URL_RE.match(text)
    if match:
        return _Board(match["tenant"], match["shard"], match["site"])
    parts = [part.strip() for part in text.split(":")]
    if len(parts) == 3 and all(parts):
        return _Board(parts[0], parts[1], parts[2])
    raise SourceError(
        "workday target must be 'tenant:shard:site' "
        f"(e.g. 'nvidia:wd5:NVIDIAExternalCareerSite') or the wday/cxs API URL; got {target!r}"
    )


def _req_id(payload: dict[str, Any]) -> str | None:
    for bullet in payload.get("bulletFields") or []:
        if isinstance(bullet, str) and bullet.strip():
            return bullet.strip()
    match = _REQ_TAIL_RE.search(payload.get("externalPath") or "")
    return match.group(1) if match else None


def _parse_date(value: Any) -> dt.datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=dt.UTC)
    except ValueError:
        return None


def _remote(remote_type: Any, location: str | None) -> bool | None:
    text = str(remote_type or "").lower()
    if "remote" in text:
        return True
    if "site" in text:  # "onSite" / "On-site"
        return False
    if location and "remote" in location.lower():
        return True
    return None


class WorkdaySource(BaseSource):
    slug: ClassVar[str] = "workday"

    def _make_http(self) -> HttpClient:
        return HttpClient(rate_limit=TokenBucket(rate=5.0, capacity=10.0))

    async def fetch(self, query: SourceQuery) -> AsyncIterator[RawPosting]:
        for target in query.targets:
            board = _parse_target(target)
            seen = 0
            offset = 0
            while seen < _MAX_POSTINGS:
                page = await self._http.post_json(
                    f"{board.base}/jobs", json_body={**_LIST_BODY, "offset": offset}
                )
                postings = page.get("jobPostings") or []
                if not postings:
                    break
                for item in postings:
                    if seen >= _MAX_POSTINGS:
                        log.warning(
                            "sources.workday.capped",
                            target=target,
                            cap=_MAX_POSTINGS,
                            total=page.get("total"),
                        )
                        return
                    seen += 1
                    yield await self._one(board, item)
                offset += len(postings)
                total = page.get("total")
                if len(postings) < _PAGE or (isinstance(total, int) and offset >= total):
                    break

    async def _one(self, board: _Board, item: dict[str, Any]) -> RawPosting:
        external_path = item.get("externalPath") or ""
        detail: dict[str, Any] | None = None
        if external_path:
            try:
                detail = await self._http.get_json(f"{board.base}{external_path}")
            except SourceError as exc:
                log.warning(
                    "sources.workday.detail_failed",
                    tenant=board.tenant,
                    path=external_path,
                    error=str(exc),
                )
        return RawPosting(
            source_slug=self.slug,
            fetched_at=dt.datetime.now(tz=dt.UTC),
            source_url=board.posting_url(external_path) if external_path else "",
            payload={
                **item,
                "_detail": detail,
                "_tenant": board.tenant,
                "_shard": board.shard,
                "_site": board.site,
            },
        )

    def parse(self, raw: RawPosting) -> CanonicalPosting:
        p = raw.payload
        board = _Board(p["_tenant"], p["_shard"], p["_site"])
        external_path = p.get("externalPath") or ""
        info: dict[str, Any] = (p.get("_detail") or {}).get("jobPostingInfo") or {}
        org: dict[str, Any] = (p.get("_detail") or {}).get("hiringOrganization") or {}

        native_id = info.get("id") or _req_id(p)
        url = info.get("externalUrl") or (board.posting_url(external_path) if external_path else "")
        if not native_id and not url:
            raise SourcePayloadError(f"workday posting has no id and no path: {p.get('title')!r}")

        location = info.get("location") or p.get("locationsText")
        html = info.get("jobDescription")
        return CanonicalPosting(
            source_slug=self.slug,
            source_job_id=str(native_id) if native_id else None,
            url=url,
            company_name=board.tenant.replace("-", " ").title(),
            title=info.get("title") or p.get("title") or "",
            location_raw=location,
            location_country=(info.get("country") or {}).get("descriptor"),
            remote=_remote(info.get("remoteType") or p.get("remoteType"), location),
            employment_type=info.get("timeType"),
            description_html=html,
            description_text=html_to_text(html),
            posted_at=_parse_date(info.get("startDate")),
            source_metadata={
                "workday_tenant": board.tenant,
                "workday_shard": board.shard,
                "workday_site": board.site,
                "workday_req_id": _req_id(p),
                "external_path": external_path,
                "remote_type": info.get("remoteType") or p.get("remoteType"),
                "additional_locations": info.get("additionalLocations") or [],
                "hiring_organization": org.get("name"),
            },
        )
