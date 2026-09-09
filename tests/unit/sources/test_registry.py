from __future__ import annotations

import pytest

from app.sources import available, get_source
from app.sources.ashby import AshbySource
from app.sources.errors import SourceError
from app.sources.greenhouse import GreenhouseSource
from app.sources.lever import LeverSource
from app.sources.workday import WorkdaySource


def test_available_lists_the_registered_slugs() -> None:
    assert available() == ["ashby", "greenhouse", "lever", "workday"]


def test_get_source_returns_the_right_adapter() -> None:
    assert isinstance(get_source("greenhouse"), GreenhouseSource)
    assert isinstance(get_source("lever"), LeverSource)
    assert isinstance(get_source("ashby"), AshbySource)
    assert isinstance(get_source("workday"), WorkdaySource)


def test_unknown_slug_raises_source_error() -> None:
    with pytest.raises(SourceError, match="unknown source"):
        get_source("monster.com")
