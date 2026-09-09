"""The spreadsheet's columns: order, headers, which are hidden, which import back.

`Title` / `Company` / `URL` are read-only context - the import ignores them.
`job_id` and `revision` are hidden: the reconcile key and the stale-write guard
(ADR-0010).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Column:
    header: str
    field: str  # attribute on ExportRow / key in a parsed import row
    hidden: bool = False
    editable: bool = False  # written back into the Application on import


COLUMNS: tuple[Column, ...] = (
    Column("Title", "title"),
    Column("Company", "company_name"),
    Column("URL", "url"),
    Column("Applied", "applied", editable=True),
    Column("Applied At", "applied_at", editable=True),
    Column("Networking", "networking", editable=True),
    Column("Outcome", "outcome", editable=True),
    Column("Application URL", "application_url", editable=True),
    Column("Notes", "notes", editable=True),
    Column("job_id", "job_id", hidden=True),
    Column("revision", "revision", hidden=True),
)

HEADERS: tuple[str, ...] = tuple(c.header for c in COLUMNS)
EDITABLE_COLUMNS: tuple[Column, ...] = tuple(c for c in COLUMNS if c.editable)
EDITABLE_FIELDS: tuple[str, ...] = tuple(c.field for c in EDITABLE_COLUMNS)
