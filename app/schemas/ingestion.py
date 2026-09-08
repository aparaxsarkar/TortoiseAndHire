"""API-facing DTOs for an ingestion run.

`SourceRunResult` is `ingestion.results.IngestionRunResult` flattened for the
wire; `IngestionService` does the mapping so nothing downstream depends on the
runner's internal dataclass.
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel


class SourceRunResult(BaseModel):
    source: str
    status: str  # success | partial | failed | skipped
    run_id: uuid.UUID | None = None
    fetched: int = 0
    matched: int = 0
    filtered_out: int = 0
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0
    failed: int = 0
    error_summary: str | None = None


class IngestionReport(BaseModel):
    results: list[SourceRunResult]
