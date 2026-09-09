from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx
import pytest
import respx

from app.schemas.canonical import RawPosting
from app.sources import JobSource, workday
from app.sources.base import SourceQuery
from app.sources.errors import SourceError, SourcePayloadError, SourceUnavailable
from app.sources.http import HttpClient
from app.sources.workday import WorkdaySource, _parse_date, _parse_target, _remote

TARGET = "acme:wd5:CareerSite"
BASE = "https://acme.wd5.myworkdayjobs.com/wday/cxs/acme/CareerSite"
LIST = f"{BASE}/jobs"
DETAIL_1 = f"{BASE}/job/US-CA-Santa-Clara/ML-Engineer_JR1001"
DETAIL_2 = f"{BASE}/job/Remote/Staff-Data-Engineer_JR1002"
DETAIL_3 = f"{BASE}/job/NYC/Old-Role_JR1003"


def _source() -> WorkdaySource:
    return WorkdaySource(HttpClient(retry_attempts=2, retry_backoff=0.0))


async def _fetch_all(src: WorkdaySource) -> list[RawPosting]:
    return [raw async for raw in src.fetch(SourceQuery(targets=[TARGET]))]


def _wire(load_fixture: Callable[[str], Any]) -> None:
    respx.post(LIST).mock(return_value=httpx.Response(200, json=load_fixture("workday/list.json")))
    respx.get(DETAIL_1).mock(
        return_value=httpx.Response(200, json=load_fixture("workday/detail-1.json"))
    )
    respx.get(DETAIL_2).mock(
        return_value=httpx.Response(200, json=load_fixture("workday/detail-2.json"))
    )
    respx.get(DETAIL_3).mock(return_value=httpx.Response(404, text="gone"))


# --- target parsing --------------------------------------------------------


def test_parse_target_triple() -> None:
    board = _parse_target("nvidia:wd5:NVIDIAExternalCareerSite")
    assert (board.tenant, board.shard, board.site) == ("nvidia", "wd5", "NVIDIAExternalCareerSite")


def test_parse_target_from_cxs_url() -> None:
    board = _parse_target("https://nvidia.wd5.myworkdayjobs.com/wday/cxs/nvidia/Ext/jobs")
    assert (board.tenant, board.shard, board.site) == ("nvidia", "wd5", "Ext")


@pytest.mark.parametrize("bad", ["nvidia", "a:b", "a::c", "https://example.com/x"])
def test_parse_target_rejects_malformed(bad: str) -> None:
    with pytest.raises(SourceError, match="workday target"):
        _parse_target(bad)


@pytest.mark.parametrize(
    ("remote_type", "location", "expected"),
    [
        ("Remote", None, True),
        ("onSite", None, False),
        (None, "Bengaluru, Remote", True),
        (None, "London", None),
    ],
)
def test_remote_helper(
    remote_type: str | None, location: str | None, expected: bool | None
) -> None:
    assert _remote(remote_type, location) is expected


def test_parse_date_ignores_junk() -> None:
    assert _parse_date("not a date") is None
    assert _parse_date("2026-09-09") is not None


# --- fetch / parse -------------------------------------------------------


def test_satisfies_the_jobsource_protocol() -> None:
    assert isinstance(WorkdaySource(), JobSource)


@respx.mock
async def test_fetch_yields_one_rawposting_per_list_item(
    load_fixture: Callable[[str], Any],
) -> None:
    _wire(load_fixture)
    src = _source()
    try:
        raws = await _fetch_all(src)
    finally:
        await src.aclose()

    assert len(raws) == 4
    assert all(r.source_slug == "workday" for r in raws)
    assert raws[0].payload["_tenant"] == "acme"


@respx.mock
async def test_parse_maps_a_full_posting(load_fixture: Callable[[str], Any]) -> None:
    _wire(load_fixture)
    src = _source()
    try:
        raws = await _fetch_all(src)
    finally:
        await src.aclose()

    posting = src.parse(raws[0])
    assert posting.source_slug == "workday"
    assert posting.source_job_id == "0a757e1f3ad3102c280a27e319640000"  # detail id
    assert (
        posting.url
        == "https://acme.wd5.myworkdayjobs.com/CareerSite/job/US-CA-Santa-Clara/ML-Engineer_JR1001"
    )
    assert posting.company_name == "Acme"
    assert posting.title == "ML Engineer"
    assert posting.location_raw == "United States, Santa Clara"
    assert posting.location_country == "United States"
    assert posting.remote is None
    assert posting.employment_type == "Full time"
    assert "<strong>" in (posting.description_html or "")
    assert "3+ years" in (posting.description_text or "")
    assert posting.posted_at is not None and posting.posted_at.isoformat().startswith("2026-09-09")
    assert posting.source_metadata["workday_req_id"] == "JR1001"
    assert posting.source_metadata["additional_locations"] == ["United States, Remote"]
    assert posting.source_metadata["hiring_organization"] == "US01 Acme Santa Clara"


@respx.mock
async def test_remote_type_remote_maps_true(load_fixture: Callable[[str], Any]) -> None:
    _wire(load_fixture)
    src = _source()
    try:
        raws = await _fetch_all(src)
    finally:
        await src.aclose()

    posting = src.parse(raws[1])
    assert posting.source_job_id == "1b1b1b1b2c2c2c2c3d3d3d3d4e4e4e4e"
    assert posting.remote is True
    assert posting.posted_at is not None and posting.posted_at.isoformat().startswith("2026-08-15")
    assert posting.source_metadata["hiring_organization"] is None


@respx.mock
async def test_detail_failure_falls_back_to_list_only(load_fixture: Callable[[str], Any]) -> None:
    _wire(load_fixture)
    src = _source()
    try:
        raws = await _fetch_all(src)
    finally:
        await src.aclose()

    posting = src.parse(raws[2])
    assert posting.source_job_id == "JR1003"  # from bulletFields, detail was 404
    assert posting.url == "https://acme.wd5.myworkdayjobs.com/CareerSite/job/NYC/Old-Role_JR1003"
    assert posting.title == "Old Role (detail unavailable)"
    assert posting.description_html is None
    assert posting.description_text is None
    assert posting.posted_at is None


@respx.mock
async def test_parse_of_a_posting_with_no_path_or_req_id_raises(
    load_fixture: Callable[[str], Any],
) -> None:
    _wire(load_fixture)
    src = _source()
    try:
        raws = await _fetch_all(src)
    finally:
        await src.aclose()

    with pytest.raises(SourcePayloadError):
        src.parse(raws[3])


@respx.mock
async def test_list_http_failure_propagates_as_unavailable() -> None:
    respx.post(LIST).mock(return_value=httpx.Response(500))
    src = _source()
    try:
        with pytest.raises(SourceUnavailable):
            await _fetch_all(src)
    finally:
        await src.aclose()


@respx.mock
async def test_empty_result_yields_nothing() -> None:
    respx.post(LIST).mock(return_value=httpx.Response(200, json={"total": 0, "jobPostings": []}))
    src = _source()
    try:
        assert await _fetch_all(src) == []
    finally:
        await src.aclose()


@respx.mock
async def test_pages_until_offset_reaches_total(load_fixture: Callable[[str], Any]) -> None:
    def _page(start: int, count: int, total: int) -> dict[str, Any]:
        return {
            "total": total,
            "jobPostings": [
                {
                    "title": f"Role {i}",
                    "externalPath": f"/job/x/Role-{i}_JR{i}",
                    "locationsText": "",
                    "postedOn": "",
                    "bulletFields": [f"JR{i}"],
                }
                for i in range(start, start + count)
            ],
        }

    respx.post(LIST).mock(
        side_effect=[
            httpx.Response(200, json=_page(0, 20, 25)),
            httpx.Response(200, json=_page(20, 5, 25)),
        ]
    )
    respx.route(method="GET", url__regex=rf"{BASE}/job/.*").mock(
        return_value=httpx.Response(200, json=load_fixture("workday/detail-1.json"))
    )

    src = _source()
    try:
        raws = await _fetch_all(src)
    finally:
        await src.aclose()

    assert len(raws) == 25


@respx.mock
async def test_stops_at_the_max_postings_cap(
    load_fixture: Callable[[str], Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(workday, "_MAX_POSTINGS", 2)
    _wire(load_fixture)
    src = _source()
    try:
        raws = await _fetch_all(src)
    finally:
        await src.aclose()

    assert len(raws) == 2  # list.json has 4, cap is 2
