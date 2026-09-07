from __future__ import annotations

import pytest

from tests.unit.ingestion.fakes import (
    FakeFilteredPostingSink,
    FakeRunStore,
    FakeSourcePostingSink,
)


@pytest.fixture
def run_store() -> FakeRunStore:
    return FakeRunStore()


@pytest.fixture
def posting_sink() -> FakeSourcePostingSink:
    return FakeSourcePostingSink()


@pytest.fixture
def filtered_sink() -> FakeFilteredPostingSink:
    return FakeFilteredPostingSink()
