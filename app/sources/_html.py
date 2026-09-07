"""Minimal HTML -> plain text, stdlib only.

Good enough to give the relevance filter and search something to read; block
tags become newlines, everything else collapses to single spaces. A richer
Markdown conversion can come later if it earns its keep.
"""

from __future__ import annotations

import re
from html import unescape
from html.parser import HTMLParser

_BLOCK = frozenset(
    {"p", "div", "br", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "section"}
)


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self._parts.append(data)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _BLOCK:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in _BLOCK:
            self._parts.append("\n")

    def text(self) -> str:
        joined = "".join(self._parts).replace("\xa0", " ")
        joined = re.sub(r"[ \t]+", " ", joined)
        joined = re.sub(r"\n[ \t]*\n+", "\n\n", joined)
        return joined.strip()


def html_to_text(html: str | None) -> str | None:
    if not html:
        return None
    parser = _TextExtractor()
    parser.feed(unescape(html))
    return parser.text() or None
