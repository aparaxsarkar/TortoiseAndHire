"""Opt-in smoke tests against the real APIs. Excluded from CI (`-m 'not live'`);
run with `pytest -m live`. Allowed to be flaky - they only tell us a board's
shape hasn't shifted under the adapter.
"""

from __future__ import annotations

import pytest

from app.sources.base import SourceQuery
from app.sources.greenhouse import GreenhouseSource
from app.sources.lever import LeverSource

pytestmark = pytest.mark.live


async def test_greenhouse_vercel_board_parses() -> None:
    src = GreenhouseSource()
    try:
        raws = [r async for r in src.fetch(SourceQuery(targets=["vercel"]))]
    finally:
        await src.aclose()
    assert raws
    posting = src.parse(raws[0])
    assert posting.source_slug == "greenhouse"
    assert posting.title
    assert posting.url.startswith("http")


async def test_lever_demo_account_parses() -> None:
    src = LeverSource()
    try:
        raws = [r async for r in src.fetch(SourceQuery(targets=["leverdemo"]))]
    finally:
        await src.aclose()
    assert raws
    posting = src.parse(raws[0])
    assert posting.source_slug == "lever"
    assert posting.title
