from __future__ import annotations

import pytest

from app.discovery.ruleset import Ruleset
from app.services.ingestion import IngestionService
from app.sources.errors import SourceError
from tests.unit.ingestion.fakes import RULESET_KW

RULESET = Ruleset(**RULESET_KW)


def _raising_source_factory(slug: str) -> object:
    raise SourceError(f"unknown source: {slug!r}")


async def test_run_source_propagates_an_unknown_slug() -> None:
    service = IngestionService(source_factory=_raising_source_factory, ruleset=RULESET)
    with pytest.raises(SourceError):
        await service.run_source("monster.com", targets=[])


async def test_run_all_isolates_a_source_that_fails_outright() -> None:
    service = IngestionService(source_factory=_raising_source_factory, ruleset=RULESET)

    report = await service.run_all(plan={"greenhouse": ["acme"], "lever": ["acme"]})

    assert [r.source for r in report.results] == ["greenhouse", "lever"]
    assert {r.status for r in report.results} == {"failed"}
    assert all(r.run_id is None for r in report.results)
    assert all("SourceError" in (r.error_summary or "") for r in report.results)


async def test_run_all_with_an_empty_plan_returns_no_results() -> None:
    service = IngestionService(source_factory=_raising_source_factory, ruleset=RULESET)
    report = await service.run_all(plan={})
    assert report.results == []
