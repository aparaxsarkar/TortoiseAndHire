"""Opt-in smoke tests against the real APIs. Excluded from CI (`-m 'not live'`);
run with `pytest -m live`. Allowed to be flaky - they only tell us a board's
shape hasn't shifted under the adapter.
"""

from __future__ import annotations

import pytest

from app.schemas.canonical import RawPosting
from app.sources.ashby import AshbySource
from app.sources.base import JobSource, SourceQuery
from app.sources.greenhouse import GreenhouseSource
from app.sources.lever import LeverSource
from app.sources.workday import WorkdaySource

pytestmark = pytest.mark.live


async def _first(src: JobSource, target: str) -> RawPosting:
    """First posting only - keeps the Workday smoke test to two HTTP calls."""
    try:
        async for raw in src.fetch(SourceQuery(targets=[target])):
            return raw
        raise AssertionError(f"{src.slug}: {target!r} returned no postings")
    finally:
        await src.aclose()


async def test_greenhouse_vercel_board_parses() -> None:
    src = GreenhouseSource()
    posting = src.parse(await _first(src, "vercel"))
    assert posting.source_slug == "greenhouse"
    assert posting.title
    assert posting.url.startswith("http")


async def test_lever_demo_account_parses() -> None:
    src = LeverSource()
    posting = src.parse(await _first(src, "leverdemo"))
    assert posting.source_slug == "lever"
    assert posting.title


async def test_ashby_posthog_board_parses() -> None:
    src = AshbySource()
    posting = src.parse(await _first(src, "posthog"))
    assert posting.source_slug == "ashby"
    assert posting.title
    assert posting.source_job_id
    assert posting.url.startswith("https://jobs.ashbyhq.com/")


async def test_workday_nvidia_tenant_parses() -> None:
    src = WorkdaySource()
    posting = src.parse(await _first(src, "nvidia:wd5:NVIDIAExternalCareerSite"))
    assert posting.source_slug == "workday"
    assert posting.title
    assert posting.source_job_id
    assert "myworkdayjobs.com" in posting.url
