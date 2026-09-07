from __future__ import annotations

from typing import get_args

from app.ingestion.results import IngestionRunResult, RunStatusName, Stage
from app.models.enums import IngestionStage, RunStatus


def test_stage_literal_matches_the_db_enum() -> None:
    assert set(get_args(Stage)) == {s.value for s in IngestionStage}


def test_run_status_literal_matches_the_db_enum() -> None:
    assert set(get_args(RunStatusName)) == {s.value for s in RunStatus}


def test_as_stats_has_every_counter() -> None:
    stats = IngestionRunResult(source_slug="greenhouse").as_stats()
    assert set(stats) == {
        "fetched",
        "matched",
        "filtered_out",
        "inserted",
        "updated",
        "unchanged",
        "failed",
    }
    assert set(stats.values()) == {0}


def test_defaults() -> None:
    result = IngestionRunResult(source_slug="lever")
    assert result.status == "running"
    assert result.run_id is None
    assert result.errors == []
