from __future__ import annotations

import pytest

from app.deduplication.url_canonical import canonicalize_url

CASES = [
    # (input, expected)
    ("https://Boards.Greenhouse.io/Acme/jobs/123", "https://boards.greenhouse.io/Acme/jobs/123"),
    ("https://x.com/j/1/", "https://x.com/j/1"),
    ("https://x.com/", "https://x.com/"),
    ("https://x.com", "https://x.com/"),
    ("https://x.com:443/j/1", "https://x.com/j/1"),
    ("http://x.com:80/j/1", "http://x.com/j/1"),
    ("https://x.com:8443/j/1", "https://x.com:8443/j/1"),
    ("https://x.com/j/1#apply", "https://x.com/j/1"),
    ("https://x.com/j/1?b=2&a=1", "https://x.com/j/1?a=1&b=2"),
    ("https://x.com/j/1?utm_source=li&utm_campaign=x&keep=yes", "https://x.com/j/1?keep=yes"),
    ("https://x.com/j/1?gh_src=abc&ref=foo&gclid=z", "https://x.com/j/1"),
    ("https://user:pw@x.com/j/1", "https://x.com/j/1"),
]


@pytest.mark.parametrize(("raw", "expected"), CASES)
def test_canonicalize(raw: str, expected: str) -> None:
    assert canonicalize_url(raw) == expected


def test_is_idempotent() -> None:
    once = canonicalize_url("https://X.com:443/a/b/?utm_source=x&z=1&a=2#frag")
    assert canonicalize_url(once) == once


def test_strips_surrounding_whitespace() -> None:
    assert canonicalize_url("  https://x.com/j/1  ") == "https://x.com/j/1"


def test_blank_input_has_no_host() -> None:
    # derive() relies on this to detect an unusable url.
    assert canonicalize_url("") == "/"
