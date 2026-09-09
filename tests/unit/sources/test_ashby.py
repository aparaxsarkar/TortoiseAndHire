from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from typing import Any

import httpx
import pytest
import respx

from app.schemas.canonical import RawPosting
from app.sources import JobSource
from app.sources.ashby import AshbySource
from app.sources.base import SourceQuery
from app.sources.errors import SourcePayloadError, SourceUnavailable
from app.sources.http import HttpClient

BOARD = "https://api.ashbyhq.com/posting-api/job-board/acme"


def _source() -> AshbySource:
    return AshbySource(HttpClient(retry_attempts=2, retry_backoff=0.0))


async def _fetch_all(src: AshbySource) -> list[RawPosting]:
    return [raw async for raw in src.fetch(SourceQuery(targets=["acme"]))]


def _raw(**payload: Any) -> RawPosting:
    return RawPosting(
        source_slug="ashby",
        fetched_at=dt.datetime(2026, 9, 1, tzinfo=dt.UTC),
        source_url=payload.get("jobUrl", ""),
        payload={"_board": "acme", **payload},
    )


def test_satisfies_the_jobsource_protocol() -> None:
    assert isinstance(AshbySource(), JobSource)


@respx.mock
async def test_fetch_yields_one_rawposting_per_job(load_fixture: Callable[[str], Any]) -> None:
    respx.get(BOARD).mock(return_value=httpx.Response(200, json=load_fixture("ashby/board.json")))
    src = _source()
    try:
        raws = await _fetch_all(src)
    finally:
        await src.aclose()

    assert len(raws) == 3
    assert all(r.source_slug == "ashby" for r in raws)
    assert raws[0].payload["_board"] == "acme"


@respx.mock
async def test_parse_maps_a_full_job(load_fixture: Callable[[str], Any]) -> None:
    respx.get(BOARD).mock(return_value=httpx.Response(200, json=load_fixture("ashby/board.json")))
    src = _source()
    try:
        raws = await _fetch_all(src)
    finally:
        await src.aclose()

    posting = src.parse(raws[0])
    assert posting.source_slug == "ashby"
    assert posting.source_job_id == "7458d4e9-da2e-47bd-98cb-adfda43d42b2"
    assert posting.url == "https://jobs.ashbyhq.com/acme/7458d4e9-da2e-47bd-98cb-adfda43d42b2"
    assert posting.company_name == "Acme"
    assert posting.title == "Machine Learning Engineer"
    assert posting.location_raw == "Remote - US"
    assert (posting.location_city, posting.location_region, posting.location_country) == (
        "New York",
        "NY",
        "United States",
    )
    assert posting.remote is True
    assert posting.employment_type == "FullTime"
    assert posting.department == "Machine Learning"
    assert "<strong>" in (posting.description_html or "")
    assert posting.description_text == "Build models. 0-2 yrs of experience."
    assert posting.posted_at is not None and posting.posted_at.year == 2026
    assert posting.source_metadata["apply_url"].endswith("/application")
    assert posting.source_metadata["secondary_locations"] == ["London"]


@respx.mock
async def test_parse_minimal_job_uses_fallbacks(load_fixture: Callable[[str], Any]) -> None:
    respx.get(BOARD).mock(return_value=httpx.Response(200, json=load_fixture("ashby/board.json")))
    src = _source()
    try:
        raws = await _fetch_all(src)
    finally:
        await src.aclose()

    posting = src.parse(raws[1])
    assert posting.source_job_id == "1b0c9a2e-3333-4444-5555-666677778888"
    assert posting.url.startswith("https://jobs.ashbyhq.com/acme/")  # jobUrl, no applyUrl
    assert posting.department == "Platform"  # falls back to team
    assert posting.remote is None
    assert posting.employment_type is None
    assert posting.posted_at is None
    assert posting.description_html is None
    assert posting.description_text == "5+ years building services."
    assert (posting.location_city, posting.location_region, posting.location_country) == (
        None,
        None,
        None,
    )


@respx.mock
async def test_parse_of_a_job_missing_its_id_raises(load_fixture: Callable[[str], Any]) -> None:
    respx.get(BOARD).mock(return_value=httpx.Response(200, json=load_fixture("ashby/board.json")))
    src = _source()
    try:
        raws = await _fetch_all(src)
    finally:
        await src.aclose()

    with pytest.raises(SourcePayloadError):
        src.parse(raws[2])


def _parse(**payload: Any) -> Any:
    return _source().parse(
        _raw(id="x", title="R", jobUrl="https://jobs.ashbyhq.com/acme/x", **payload)
    )


def test_onsite_workplace_type_maps_remote_false() -> None:
    assert _parse(workplaceType="OnSite", location="Austin, TX").remote is False


def test_remote_workplace_type_without_is_remote_flag_maps_true() -> None:
    assert _parse(workplaceType="Remote", location="Anywhere").remote is True


def test_remote_inferred_from_location_string() -> None:
    assert _parse(location="Remote - EU").remote is True


def test_an_unparseable_published_at_is_ignored() -> None:
    assert _parse(publishedAt="last tuesday").posted_at is None


@respx.mock
async def test_http_failure_propagates_as_unavailable() -> None:
    respx.get(BOARD).mock(return_value=httpx.Response(503))
    src = _source()
    try:
        with pytest.raises(SourceUnavailable):
            await _fetch_all(src)
    finally:
        await src.aclose()


@respx.mock
async def test_empty_board_yields_nothing() -> None:
    respx.get(BOARD).mock(return_value=httpx.Response(200, json={"apiVersion": "1", "jobs": []}))
    src = _source()
    try:
        assert await _fetch_all(src) == []
    finally:
        await src.aclose()
