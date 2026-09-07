"""Shared test fixtures."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
import structlog

from app.core.config import get_settings
from app.core.observability import metrics


@pytest.fixture(autouse=True)
def _isolate_global_state() -> Iterator[None]:
    """structlog config, the cached Settings, and the metrics registry are all
    process-global; reset them around every test so order can't matter."""
    get_settings.cache_clear()
    metrics.reset()
    yield
    structlog.reset_defaults()
    get_settings.cache_clear()
    metrics.reset()
