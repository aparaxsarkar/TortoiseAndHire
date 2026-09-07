"""What a run produced. Plain data - no DB, no ORM.

`IngestionRunResult` is the runner's return value and also the shape of the
`ingestion_runs.stats` JSONB blob (via `as_stats()`). `Stage` / `RunStatusName`
mirror the `IngestionStage` / `RunStatus` DB CHECK vocabularies exactly; a unit
test pins them together so they can't drift.
"""

from __future__ import annotations

import dataclasses
import uuid
from typing import Literal

Stage = Literal["fetch", "parse", "validate", "identity", "relevance", "persist"]
RunStatusName = Literal["running", "success", "partial", "failed", "skipped"]


@dataclasses.dataclass(slots=True)
class PostingError:
    """One posting skipped mid-run. Becomes an `ingestion_errors` row."""

    stage: Stage
    source_ref: str | None
    error_type: str
    message: str


@dataclasses.dataclass(slots=True)
class IngestionRunResult:
    source_slug: str
    status: RunStatusName = "running"
    run_id: uuid.UUID | None = None
    fetched: int = 0
    matched: int = 0
    filtered_out: int = 0
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0
    failed: int = 0
    error_summary: str | None = None
    errors: list[PostingError] = dataclasses.field(default_factory=list)

    def as_stats(self) -> dict[str, int]:
        return {
            "fetched": self.fetched,
            "matched": self.matched,
            "filtered_out": self.filtered_out,
            "inserted": self.inserted,
            "updated": self.updated,
            "unchanged": self.unchanged,
            "failed": self.failed,
        }
