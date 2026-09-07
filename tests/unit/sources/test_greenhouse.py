from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx
import pytest
import respx

from app.sources import JobSource
from app.sources.base import SourceQuery
from app.sources.errors import SourcePayloadError
from app.sources.greenhouse import GreenhouseSource
from app.sources.http import HttpClient

BOARD = "https://boards-api.greenhouse.io/v1/boards/acme"
JOBS = "https://boards-api.greenhouse.io/v1/boards/acme/jobs"


def _source() -> GreenhouseSource:
    return GreenhouseSource(HttpClient(retry_attempts=2, retry_backoff=0.0))


async def _fetch_all(src: GreenhouseSource) -> list[Any]:
    return [raw async for raw in src.fetch(SourceQuery(targets=["acme"]))]


def test_satisfies_the_jobsource_protocol() -> None:
    assert isinstance(GreenhouseSource(), JobSource)


@respx.mock
async def test_fetch_yields_one_rawposting_per_job(load_fixture: Callable[[str], Any]) -> None:
    respx.get(BOARD).mock(
        return_value=httpx.Response(200, json=load_fixture("greenhouse/board.json"))
    )
    respx.get(JOBS).mock(
        return_value=httpx.Response(200, json=load_fixture("greenhouse/jobs.json"))
    )

    src = _source()
    try:
        raws = await _fetch_all(src)
    finally:
        await src.aclose()

    assert len(raws) == 3
    assert all(r.source_slug == "greenhouse" for r in raws)
    assert raws[0].payload["_company_name"] == "Acme Corp"


@respx.mock
async def test_parse_maps_a_full_job(load_fixture: Callable[[str], Any]) -> None:
    respx.get(BOARD).mock(
        return_value=httpx.Response(200, json=load_fixture("greenhouse/board.json"))
    )
    respx.get(JOBS).mock(
        return_value=httpx.Response(200, json=load_fixture("greenhouse/jobs.json"))
    )

    src = _source()
    try:
        raws = await _fetch_all(src)
    finally:
        await src.aclose()

    posting = src.parse(raws[0])
    assert posting.source_slug == "greenhouse"
    assert posting.source_job_id == "5001"
    assert posting.url == "https://boards.greenhouse.io/acme/jobs/5001"
    assert posting.company_name == "Acme Corp"
    assert posting.title == "Machine Learning Engineer"
    assert posting.location_raw == "Remote - US"
    assert posting.remote is True
    assert posting.department == "Machine Learning"
    assert posting.description_text is not None
    assert "0-2 yrs" in posting.description_text
    assert "<strong>" in (posting.description_html or "")
    assert posting.posted_at is not None
    assert posting.source_metadata["requisition_id"] == "REQ-42"
    assert posting.source_metadata["offices"] == ["New York"]


@respx.mock
async def test_parse_of_a_job_missing_its_id_raises(load_fixture: Callable[[str], Any]) -> None:
    respx.get(BOARD).mock(
        return_value=httpx.Response(200, json=load_fixture("greenhouse/board.json"))
    )
    respx.get(JOBS).mock(
        return_value=httpx.Response(200, json=load_fixture("greenhouse/jobs.json"))
    )

    src = _source()
    try:
        raws = await _fetch_all(src)
    finally:
        await src.aclose()

    with pytest.raises(SourcePayloadError):
        src.parse(raws[2])


@respx.mock
async def test_board_without_a_name_falls_back_to_the_token(
    load_fixture: Callable[[str], Any],
) -> None:
    respx.get(BOARD).mock(return_value=httpx.Response(200, json={}))
    respx.get(JOBS).mock(
        return_value=httpx.Response(200, json=load_fixture("greenhouse/jobs.json"))
    )

    src = _source()
    try:
        raws = await _fetch_all(src)
    finally:
        await src.aclose()

    assert src.parse(raws[0]).company_name == "acme"
