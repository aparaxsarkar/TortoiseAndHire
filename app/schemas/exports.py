"""DTOs for the Excel round-trip (ADR-0005 revised, ADR-0010, ADR-0013).

`ExportRow` is one spreadsheet row on the way out. `ImportReport` is what a
`POST /exports/import` returns - a per-row account of what a commit would (or
did) change. `changes` are ordinary application-field edits; `canonical_changes`
(Title/Company/URL - ADR-0013) are reported and counted separately so they
can't be missed inside a routine status update.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field

RowAction = Literal["created", "updated", "unchanged", "conflict", "error"]


class ExportRow(BaseModel):
    job_id: uuid.UUID
    title: str
    company_name: str
    url: str | None = None
    applied: bool = False
    applied_at: dt.datetime | None = None
    networking: str = "none"
    outcome: str = "none"
    application_url: str | None = None
    notes: str | None = None
    revision: int = 0  # 0 == no application row yet


class ImportRowChange(BaseModel):
    field: str
    old: Any = None
    new: Any = None


class ImportRowResult(BaseModel):
    row: int  # 1-based spreadsheet row number
    job_id: uuid.UUID | None = None
    action: RowAction  # describes the `applications` row only - see canonical_changes
    changes: list[ImportRowChange] = Field(default_factory=list)
    canonical_changes: list[ImportRowChange] = Field(default_factory=list)
    message: str | None = None


class ImportReport(BaseModel):
    filename: str
    committed: bool
    counts: dict[RowAction, int]
    canonical_change_count: int = 0  # rows with a Title/Company/URL edit - always worth a look
    rows: list[ImportRowResult]
