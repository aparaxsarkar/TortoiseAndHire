from __future__ import annotations

import pytest

from app.discovery.experience import parse_min_years

REQUIRES = [
    ("5+ years", 5),
    ("5+ years of experience", 5),
    ("Minimum 5 years experience", 5),
    ("minimum of 5 years", 5),
    ("at least 3 years of relevant experience", 3),
    ("requires 4 years experience", 4),
    ("3-5 years of experience", 3),
    ("3 to 7 years", 3),
    ("2–4 yrs experience", 2),
    ("two years of experience", 2),
    ("seven+ years", 7),
    ("8 yrs professional experience", 8),
    # lowest requirement wins when several are mentioned
    ("2+ years of Python; 5+ years overall", 2),
]

NOT_A_REQUIREMENT = [
    "",
    "You will grow a lot in your first year.",
    "graduated within the last 5 years",  # bare number, no qualifier / no 'experience'
    "5 years ago the team was founded",
    "a 3 year roadmap",
]


@pytest.mark.parametrize(("text", "expected"), REQUIRES)
def test_parses_a_requirement(text: str, expected: int) -> None:
    assert parse_min_years(text) == expected


def test_zero_bound_range_returns_zero() -> None:
    assert parse_min_years("0-2 years of experience") == 0


@pytest.mark.parametrize("text", NOT_A_REQUIREMENT)
def test_no_requirement_returns_none(text: str) -> None:
    assert parse_min_years(text) is None
