"""The deterministic relevance filter (ADR-0009).

`evaluate(posting, ruleset)` runs between identity derivation and persistence.
It combines three signals - the title's function, seniority tokens *in the
title only*, and a parsed minimum-experience requirement - plus optional
internship and location gates. It is not a substring scan of the description.

Bias: a posting whose title matches a target function and trips no reject rule
is kept. If nothing corroborates "early career", the match is `weak` (kept, but
a downstream ranker should rank it lower).
"""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.discovery.experience import parse_min_years
from app.discovery.ruleset import Ruleset
from app.schemas.canonical import CanonicalPosting

Strength = Literal["strong", "weak"]


class RelevanceVerdict(BaseModel):
    matched: bool
    strength: Strength
    reasons: list[str]
    signals: dict[str, Any] = Field(default_factory=dict)
    ruleset_version: str


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def _title_has_word(title_norm: str, token: str) -> bool:
    return re.search(rf"\b{re.escape(token.lower())}\b", title_norm) is not None


def _is_internship(posting: CanonicalPosting, title_norm: str) -> bool:
    if posting.employment_type and "intern" in posting.employment_type.lower():
        return True
    return re.search(r"\bintern(ship)?\b", title_norm) is not None


def _location_ok(posting: CanonicalPosting, locations: list[str]) -> bool:
    if posting.remote is True:
        return True
    haystack = " ".join(
        part.lower()
        for part in (
            posting.location_raw,
            posting.location_city,
            posting.location_region,
            posting.location_country,
        )
        if part
    )
    if not haystack:
        return True  # unknown location -> keep (bias)
    return any(loc.lower() in haystack for loc in locations)


def evaluate(posting: CanonicalPosting, ruleset: Ruleset) -> RelevanceVerdict:
    title_norm = _norm(posting.title)
    reasons: list[str] = []
    signals: dict[str, Any] = {}

    matched_function = next(
        (fn for fn in ruleset.target_functions if _norm(fn) in title_norm), None
    )
    signals["matched_function"] = matched_function

    detected_seniority = next(
        (tok for tok in ruleset.exclude_title_tokens if _title_has_word(title_norm, tok)), None
    )
    signals["detected_seniority"] = detected_seniority

    min_years = parse_min_years(posting.description_text)
    signals["parsed_min_years"] = min_years

    internship = _is_internship(posting, title_norm)
    signals["internship"] = internship

    level_hit = next((lvl for lvl in ruleset.target_levels if lvl.lower() in title_norm), None)
    signals["level_hit"] = level_hit

    if matched_function is None:
        reasons.append("title_not_target")
    if detected_seniority is not None:
        reasons.append("seniority_excluded")
    if min_years is not None and min_years > ruleset.max_experience_years:
        reasons.append("experience_over_threshold")
    if internship and not ruleset.include_internships:
        reasons.append("internship_excluded")
    if ruleset.locations and not _location_ok(posting, ruleset.locations):
        reasons.append("location_excluded")

    matched = not reasons
    corroborated = (
        level_hit is not None
        or (min_years is not None and min_years <= ruleset.max_experience_years)
        or posting.remote is True
    )
    strength: Strength = "strong" if (matched and corroborated) else "weak"

    return RelevanceVerdict(
        matched=matched,
        strength=strength,
        reasons=reasons,
        signals=signals,
        ruleset_version=ruleset.version,
    )
