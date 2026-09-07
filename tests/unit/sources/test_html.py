from __future__ import annotations

from app.sources._html import html_to_text


def test_none_and_empty() -> None:
    assert html_to_text(None) is None
    assert html_to_text("") is None
    assert html_to_text("   ") is None


def test_strips_tags_and_decodes_entities() -> None:
    out = html_to_text("<p>Build&nbsp;models &amp; ship.</p>")
    assert out == "Build models & ship."


def test_block_tags_become_newlines() -> None:
    out = html_to_text("<h2>About</h2><p>Line one.</p><ul><li>a</li><li>b</li></ul>")
    assert out is not None
    assert "About" in out
    assert "Line one." in out
    assert "\n" in out


def test_collapses_runs_of_whitespace() -> None:
    assert html_to_text("<p>a    b\t\tc</p>") == "a b c"
