from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.jobs import JobFilters


def test_defaults() -> None:
    f = JobFilters()
    assert (f.limit, f.offset) == (50, 0)
    assert f.q is None and f.remote is None


@pytest.mark.parametrize("bad", [{"limit": 0}, {"limit": 201}, {"offset": -1}])
def test_pagination_bounds_are_enforced(bad: dict[str, int]) -> None:
    with pytest.raises(ValidationError):
        JobFilters(**bad)
