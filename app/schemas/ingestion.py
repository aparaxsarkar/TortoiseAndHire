"""DTOs for triggering and inspecting ingestion runs.

`SourceRunResult` is `ingestion.results.IngestionRunResult` flattened for the
wire; `IngestionService` does the mapping so nothing downstream depends on the
runner's internal dataclass.
"""

from __future__ import annotations

import datetime as dt
import uuid

from pydantic import BaseModel, Field, model_validator


class RunRequest(BaseModel):
    """`POST /ingestion/runs` body. Either one source with its targets, or a
    whole `{slug: targets}` plan - not both, not neither."""

    source: str | None = None
    targets: list[str] = Field(default_factory=list)
    plan: dict[str, list[str]] | None = None

    @model_validator(mode="after")
    def _exactly_one_shape(self) -> RunRequest:
        if (self.source is None) == (self.plan is None):
            raise ValueError("provide either `source` (with `targets`) or `plan`, not both")
        return self


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


class IngestionRunSummary(BaseModel):
    id: uuid.UUID
    source: str
    trigger: str
    status: str
    started_at: dt.datetime
    finished_at: dt.datetime | None = None
    stats: dict[str, int] = Field(default_factory=dict)
    error_summary: str | None = None
