"""The spreadsheet's columns: order, headers, which are hidden, which import back.

Two kinds of column round-trip (`editable=True`) (ADR-0013):

- **Application** columns (`Applied` ... `Notes`) write to *my* `applications`
  row - the ordinary case, silent in the report when they're the only change.
- **Canonical** columns (`Title`, `Company`, `URL`) write to the *shared*
  `jobs` / `companies` / `source_postings` record - a correction for a bad
  scrape, not a status update. They're rarer and higher-blast-radius, so the
  service always reports them separately and loudly (`canonical_changes`),
  never folds them into an ordinary "updated" the way application fields are.

`job_id` and `revision` are hidden: the reconcile key and the stale-write guard
(ADR-0010, application fields only - there's no revision lock on canonical
fields, see ADR-0013).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Column:
    header: str
    field: str  # attribute on ExportRow / key in a parsed import row
    hidden: bool = False
    editable: bool = False  # round-trips on import (either kind, below)
    canonical: bool = False  # writes to jobs/companies/source_postings, not applications


COLUMNS: tuple[Column, ...] = (
    Column("Title", "title", editable=True, canonical=True),
    Column("Company", "company_name", editable=True, canonical=True),
    Column("URL", "url", editable=True, canonical=True),
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
CANONICAL_COLUMNS: tuple[Column, ...] = tuple(c for c in EDITABLE_COLUMNS if c.canonical)
APPLICATION_COLUMNS: tuple[Column, ...] = tuple(c for c in EDITABLE_COLUMNS if not c.canonical)
CANONICAL_FIELDS: tuple[str, ...] = tuple(c.field for c in CANONICAL_COLUMNS)
APPLICATION_FIELDS: tuple[str, ...] = tuple(c.field for c in APPLICATION_COLUMNS)
