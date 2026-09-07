from __future__ import annotations

from pathlib import Path

import pytest

from app.discovery.rules import evaluate
from app.discovery.ruleset import Ruleset, load_ruleset
from app.schemas.canonical import CanonicalPosting

REPO_ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def ruleset() -> Ruleset:
    return load_ruleset(REPO_ROOT / "config" / "discovery.yml")


def posting(**kw: object) -> CanonicalPosting:
    base: dict[str, object] = {
        "source_slug": "greenhouse",
        "url": "https://x/1",
        "company_name": "Acme",
        "title": "Machine Learning Engineer",
    }
    base.update(kw)
    return CanonicalPosting(**base)  # type: ignore[arg-type]


# --- the six worked examples from the blueprint / ADR-0009 --------------------


def test_ml_engineer_early_career_is_a_strong_keep(ruleset: Ruleset) -> None:
    v = evaluate(
        posting(
            title="Machine Learning Engineer",
            description_text="Master's preferred, 0-2 yrs of experience",
        ),
        ruleset,
    )
    assert v.matched is True
    assert v.strength == "strong"
    assert v.reasons == []


def test_five_plus_years_is_rejected(ruleset: Ruleset) -> None:
    v = evaluate(
        posting(
            title="Software Engineer, AI Platform",
            description_text="5+ years of experience required",
        ),
        ruleset,
    )
    assert v.matched is False
    assert "experience_over_threshold" in v.reasons
    assert v.signals["parsed_min_years"] == 5


def test_senior_in_title_is_rejected(ruleset: Ruleset) -> None:
    v = evaluate(posting(title="Senior Software Engineer"), ruleset)
    assert v.matched is False
    assert v.reasons == ["seniority_excluded"]
    assert v.signals["detected_seniority"] == "senior"


def test_staff_in_title_is_rejected(ruleset: Ruleset) -> None:
    v = evaluate(posting(title="Staff ML Engineer"), ruleset)
    assert v.matched is False
    assert "seniority_excluded" in v.reasons


def test_non_target_function_is_rejected(ruleset: Ruleset) -> None:
    v = evaluate(posting(title="HR Business Partner"), ruleset)
    assert v.matched is False
    assert v.reasons == ["title_not_target"]
    assert v.signals["matched_function"] is None


def test_bare_function_match_is_a_weak_keep(ruleset: Ruleset) -> None:
    v = evaluate(posting(title="Software Engineer", description_text=""), ruleset)
    assert v.matched is True
    assert v.strength == "weak"


# --- edge cases -------------------------------------------------------------


def test_seniority_word_in_the_body_does_not_reject(ruleset: Ruleset) -> None:
    v = evaluate(
        posting(
            title="Software Engineer",
            description_text="You'll pair with senior engineers and staff architects.",
        ),
        ruleset,
    )
    assert v.matched is True
    assert v.signals["detected_seniority"] is None


def test_target_level_in_title_makes_it_strong(ruleset: Ruleset) -> None:
    v = evaluate(posting(title="Junior Data Engineer"), ruleset)
    assert v.matched is True
    assert v.strength == "strong"
    assert v.signals["level_hit"] == "junior"


def test_remote_corroborates_strength(ruleset: Ruleset) -> None:
    v = evaluate(posting(title="Software Engineer", remote=True), ruleset)
    assert v.matched is True
    assert v.strength == "strong"


def test_ambiguous_experience_phrasing_keeps_the_posting(ruleset: Ruleset) -> None:
    v = evaluate(
        posting(title="Data Engineer", description_text="the platform was rebuilt 5 years ago"),
        ruleset,
    )
    assert v.matched is True
    assert v.signals["parsed_min_years"] is None


def test_internship_excluded_when_ruleset_disallows() -> None:
    rs = Ruleset(
        version="t",
        target_functions=["software engineer"],
        include_internships=False,
    )
    v = evaluate(posting(title="Software Engineer Intern"), rs)
    assert v.matched is False
    assert v.reasons == ["internship_excluded"]


def test_internship_kept_when_ruleset_allows() -> None:
    rs = Ruleset(version="t", target_functions=["software engineer"], include_internships=True)
    v = evaluate(posting(title="Software Engineering Internship"), rs)
    assert v.matched is True


def test_internship_detected_via_employment_type() -> None:
    rs = Ruleset(version="t", target_functions=["software engineer"], include_internships=False)
    v = evaluate(
        posting(title="Software Engineer", employment_type="Internship"),
        rs,
    )
    assert v.reasons == ["internship_excluded"]


def test_location_excluded_when_not_in_allowed_list() -> None:
    rs = Ruleset(
        version="t",
        target_functions=["software engineer"],
        locations=["united states", "remote"],
    )
    v = evaluate(posting(title="Software Engineer", location_raw="London, UK", remote=False), rs)
    assert v.matched is False
    assert v.reasons == ["location_excluded"]


def test_remote_passes_the_location_gate() -> None:
    rs = Ruleset(version="t", target_functions=["software engineer"], locations=["united states"])
    v = evaluate(posting(title="Software Engineer", location_raw="London, UK", remote=True), rs)
    assert v.matched is True


def test_unknown_location_is_kept() -> None:
    rs = Ruleset(version="t", target_functions=["software engineer"], locations=["united states"])
    v = evaluate(posting(title="Software Engineer"), rs)  # no location fields at all
    assert v.matched is True


def test_multiple_reasons_are_all_reported(ruleset: Ruleset) -> None:
    v = evaluate(
        posting(title="Principal HR Manager", description_text="10+ years experience"),
        ruleset,
    )
    assert v.matched is False
    assert set(v.reasons) >= {"title_not_target", "seniority_excluded", "experience_over_threshold"}


def test_ruleset_version_is_carried_through(ruleset: Ruleset) -> None:
    v = evaluate(posting(title="Software Engineer"), ruleset)
    assert v.ruleset_version == ruleset.version
