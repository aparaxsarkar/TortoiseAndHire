"""Deterministic source-posting identity (ADR-0002).

`derive()` produces the `(source, dedup_key)` that the DB `UNIQUE` constraint is
built on: the provider's own id when there is one, otherwise the canonicalised
URL. `content_hash()` is the change signal the upsert uses to tell an "updated"
posting from an unchanged re-ingest.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from urllib.parse import urlsplit

from app.core.errors import TortoiseError
from app.deduplication.url_canonical import canonicalize_url
from app.schemas.canonical import CanonicalPosting


class IdentityError(TortoiseError):
    """A posting has neither a usable source_job_id nor a usable URL."""


@dataclass(frozen=True, slots=True)
class PostingIdentity:
    source_slug: str
    source_job_id: str | None
    canonical_url: str
    dedup_key: str


def derive(posting: CanonicalPosting) -> PostingIdentity:
    sjid = (posting.source_job_id or "").strip() or None

    canonical_url = canonicalize_url(posting.url)
    if not urlsplit(canonical_url).netloc:
        canonical_url = ""

    if sjid is None and not canonical_url:
        raise IdentityError(
            f"posting from {posting.source_slug!r} has no source_job_id and no usable url "
            f"(url={posting.url!r})"
        )

    dedup_key = sjid if sjid is not None else canonical_url
    return PostingIdentity(posting.source_slug, sjid, canonical_url, dedup_key)


_CONTENT_FIELDS = (
    "title",
    "company_name",
    "company_domain",
    "location_raw",
    "location_city",
    "location_region",
    "location_country",
    "remote",
    "employment_type",
    "department",
    "description_text",
    "compensation_raw",
)


def content_hash(posting: CanonicalPosting) -> str:
    data: dict[str, object] = {f: getattr(posting, f) for f in _CONTENT_FIELDS}
    data["posted_at"] = posting.posted_at.isoformat() if posting.posted_at else None
    blob = json.dumps(data, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()
