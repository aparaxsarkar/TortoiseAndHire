from __future__ import annotations

from pathlib import Path

import pytest

from app.sources.registry import available
from scripts.run_ingestion import load_plan

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_load_plan_reads_the_checked_in_config() -> None:
    plan = load_plan(REPO_ROOT / "config" / "sources.yml")
    assert set(plan) <= set(available())
    assert plan  # not empty
    assert all(isinstance(targets, list) and targets for targets in plan.values())


def test_load_plan_rejects_an_unknown_source(tmp_path: Path) -> None:
    path = tmp_path / "sources.yml"
    path.write_text("sources:\n  monster:\n    - some-token\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="monster"):
        load_plan(path)


def test_load_plan_skips_sources_with_no_targets(tmp_path: Path) -> None:
    path = tmp_path / "sources.yml"
    path.write_text("sources:\n  greenhouse: []\n  lever:\n    - acme\n", encoding="utf-8")
    assert load_plan(path) == {"lever": ["acme"]}


def test_load_plan_handles_an_empty_file(tmp_path: Path) -> None:
    path = tmp_path / "sources.yml"
    path.write_text("", encoding="utf-8")
    assert load_plan(path) == {}
