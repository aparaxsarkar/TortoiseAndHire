from __future__ import annotations

import datetime as dt

import pytest

from app.deduplication.identity import IdentityError, content_hash, derive
from app.schemas.canonical import CanonicalPosting


def make(**kw: object) -> CanonicalPosting:
    base: dict[str, object] = {
        "source_slug": "greenhouse",
        "url": "https://boards.greenhouse.io/acme/jobs/42?utm_source=x",
        "company_name": "Acme",
        "title": "Machine Learning Engineer",
    }
    base.update(kw)
    return CanonicalPosting(**base)  # type: ignore[arg-type]


def test_dedup_key_prefers_source_job_id() -> None:
    ident = derive(make(source_job_id="  gh-42  "))
    assert ident.source_job_id == "gh-42"
    assert ident.dedup_key == "gh-42"
    assert ident.canonical_url == "https://boards.greenhouse.io/acme/jobs/42"


def test_dedup_key_falls_back_to_canonical_url() -> None:
    ident = derive(make(source_job_id=None))
    assert ident.source_job_id is None
    assert ident.dedup_key == "https://boards.greenhouse.io/acme/jobs/42"


def test_blank_source_job_id_is_treated_as_absent() -> None:
    ident = derive(make(source_job_id="   "))
    assert ident.source_job_id is None
    assert ident.dedup_key.startswith("https://")


def test_raises_when_no_id_and_no_usable_url() -> None:
    with pytest.raises(IdentityError):
        derive(make(source_job_id=None, url="not a url"))


def test_raises_on_empty_url_without_id() -> None:
    with pytest.raises(IdentityError):
        derive(make(source_job_id="", url=""))


def test_content_hash_is_stable_and_order_independent() -> None:
    a = make(
        description_text="Build models.", location_raw="Remote", posted_at=dt.datetime(2026, 1, 1)
    )
    b = make(
        posted_at=dt.datetime(2026, 1, 1), location_raw="Remote", description_text="Build models."
    )
    assert content_hash(a) == content_hash(b)


def test_content_hash_changes_when_a_content_field_changes() -> None:
    a = make(description_text="v1")
    b = make(description_text="v2")
    assert content_hash(a) != content_hash(b)


def test_content_hash_ignores_url_and_source_metadata() -> None:
    a = make(url="https://x/1", source_metadata={"raw": 1})
    b = make(url="https://x/2?utm_source=q", source_metadata={"raw": 999})
    assert content_hash(a) == content_hash(b)
