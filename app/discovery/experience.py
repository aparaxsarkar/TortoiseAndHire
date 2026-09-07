"""Parse a stated minimum years-of-experience requirement out of free text.

Returns the lowest number of years the text plausibly *requires*, or None when
nothing reads as a requirement. Bias is toward None (keep the posting): a bare
"5 years" with no qualifier and no "experience" nearby is treated as ambiguous,
not a requirement.
"""

from __future__ import annotations

import re

_WORD_NUMBERS = {
    "zero": 0,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
}

_YEARS = r"(?:years?|yrs?)"

# "3-5 years", "3 to 5 years", "3–5 yrs" -> the lower bound is the minimum.
_RANGE = re.compile(rf"(\d{{1,2}})\s*(?:-|–|—|to)\s*\d{{1,2}}\s*\+?\s*{_YEARS}\b", re.IGNORECASE)

# "5+ years", "minimum 5 years", "at least 5 yrs", "5 years of experience".
_SINGLE = re.compile(
    rf"(minimum|min\.?|at least|>=|over|requires?|require)?\s*(?:of\s+)?"
    rf"(\d{{1,2}})(\s*\+)?\s*{_YEARS}\b"
    rf"(\s*(?:of\s+)?(?:relevant\s+|professional\s+|industry\s+|work\s+|hands-on\s+)?"
    rf"(?:experience|exp)\b)?",
    re.IGNORECASE,
)

_WORD = re.compile(
    rf"\b({'|'.join(_WORD_NUMBERS)})(\s*\+)?\s*{_YEARS}\b"
    rf"(\s*(?:of\s+)?(?:experience|exp)\b)?",
    re.IGNORECASE,
)


def parse_min_years(text: str | None) -> int | None:
    if not text:
        return None

    candidates: list[int] = []

    for m in _RANGE.finditer(text):
        candidates.append(int(m.group(1)))

    for m in _SINGLE.finditer(text):
        qualifier, number, plus, experience = m.groups()
        if qualifier or plus or experience:
            candidates.append(int(number))

    for m in _WORD.finditer(text):
        word, plus, experience = m.groups()
        if plus or experience:
            candidates.append(_WORD_NUMBERS[word.lower()])

    return min(candidates) if candidates else None
