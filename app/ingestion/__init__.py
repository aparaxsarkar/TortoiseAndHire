"""Run orchestration: fetch -> pipeline -> relevance gate -> persist -> run log.

ORM-free by construction (ADR-0011): everything that writes goes through a port
in `ports.py`, implemented against real repositories in `app/services/ingestion.py`.
"""

from __future__ import annotations

from app.ingestion.pipeline import PipelineError, PreparedPosting, prepare
from app.ingestion.ports import (
    FilteredPostingSink,
    PersistOutcome,
    RunStore,
    SourcePostingSink,
)
from app.ingestion.results import IngestionRunResult, PostingError
from app.ingestion.runner import IngestionRunner

__all__ = [
    "FilteredPostingSink",
    "IngestionRunResult",
    "IngestionRunner",
    "PersistOutcome",
    "PipelineError",
    "PostingError",
    "PreparedPosting",
    "RunStore",
    "SourcePostingSink",
    "prepare",
]
