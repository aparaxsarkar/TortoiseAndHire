from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx
import pytest
import respx

from app.sources import JobSource
from app.sources.base import SourceQuery
from app.sources.errors import SourcePayloadError
from app.sources.http import HttpClient
from app.sources.lever import LeverSource

POSTINGS = "https://api.lever.co/v0/postings/acme"


def _source() -> LeverSource:
    return LeverSource(HttpClient(retry_attempts=2, retry_backoff=0.0))


async def _fetch_all(src: LeverSource) -> list[Any]:
    return [raw async for raw in src.fetch(SourceQuery(targets=["acme"]))]


def test_satisfies_the_jobsource_protocol() -> None:
    assert isinstance(LeverSource(), JobSource)


@respx.mock
async def test_fetch_and_parse_a_full_posting(load_fixture: Callable[[str], Any]) -> None:
    respx.get(POSTINGS).mock(
        return_value=httpx.Response(200, json=load_fixture("lever/postings.json"))
    )
    src = _source()
    try:
        raws = await _fetch_all(src)
    finally:
        await src.aclose()

    assert len(raws) == 3
    posting = src.parse(raws[0])
    assert posting.source_slug == "lever"
    assert posting.source_job_id == "11111111-2222-3333-4444-555555555555"
    assert posting.url == "https://jobs.lever.co/acme/11111111-2222-3333-4444-555555555555"
    assert posting.company_name == "Acme"
    assert posting.title == "Data Engineer"
    assert posting.location_raw == "New York"
    assert posting.department == "Engineering"
    assert posting.employment_type == "Full-time"
    assert posting.remote is True
    assert posting.description_text == "Own the pipeline.\n\nWe use Postgres."
    assert posting.posted_at is not None
    assert posting.source_metadata["lever_account"] == "acme"
    assert posting.source_metadata["lists"] == ["What you'll do"]


@respx.mock
async def test_on_site_posting_and_apply_url_fallback(load_fixture: Callable[[str], Any]) -> None:
    respx.get(POSTINGS).mock(
        return_value=httpx.Response(200, json=load_fixture("lever/postings.json"))
    )
    src = _source()
    try:
        raws = await _fetch_all(src)
    finally:
        await src.aclose()

    posting = src.parse(raws[1])
    assert posting.remote is False
    assert posting.url.endswith("/apply")
    assert posting.description_text == "8+ years of experience."


@respx.mock
async def test_posting_missing_its_id_raises(load_fixture: Callable[[str], Any]) -> None:
    respx.get(POSTINGS).mock(
        return_value=httpx.Response(200, json=load_fixture("lever/postings.json"))
    )
    src = _source()
    try:
        raws = await _fetch_all(src)
    finally:
        await src.aclose()

    with pytest.raises(SourcePayloadError):
        src.parse(raws[2])
