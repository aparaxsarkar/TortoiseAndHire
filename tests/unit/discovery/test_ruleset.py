from __future__ import annotations

from pathlib import Path

import pytest

from app.discovery.ruleset import Ruleset, load_ruleset

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_loads_the_checked_in_ruleset() -> None:
    rs = load_ruleset(REPO_ROOT / "config" / "discovery.yml")
    assert isinstance(rs, Ruleset)
    assert rs.version
    assert "machine learning engineer" in rs.target_functions
    assert "senior" in rs.exclude_title_tokens
    assert rs.max_experience_years == 3


def test_frozen() -> None:
    rs = load_ruleset(REPO_ROOT / "config" / "discovery.yml")
    with pytest.raises(Exception):  # noqa: B017 - pydantic ValidationError on frozen set
        rs.version = "nope"  # type: ignore[misc]


def test_rejects_non_mapping(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yml"
    bad.write_text("- just\n- a\n- list\n", encoding="utf-8")
    with pytest.raises(ValueError, match="mapping"):
        load_ruleset(bad)


def test_rejects_unknown_key(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yml"
    bad.write_text("version: '1'\ntarget_functions: [x]\nsurprise: 1\n", encoding="utf-8")
    with pytest.raises(Exception):  # noqa: B017 - pydantic ValidationError, extra='forbid'
        load_ruleset(bad)


def test_requires_version_and_target_functions(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yml"
    bad.write_text("target_levels: [junior]\n", encoding="utf-8")
    with pytest.raises(Exception):  # noqa: B017
        load_ruleset(bad)


def test_defaults(tmp_path: Path) -> None:
    ok = tmp_path / "ok.yml"
    ok.write_text("version: '1'\ntarget_functions: [data engineer]\n", encoding="utf-8")
    rs = load_ruleset(ok)
    assert rs.max_experience_years == 3
    assert rs.include_internships is False
    assert rs.locations is None
    assert rs.target_levels == []
