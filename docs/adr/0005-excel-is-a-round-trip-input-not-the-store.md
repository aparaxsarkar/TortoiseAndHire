# ADR-0005: Excel is a round-trip input, not the store (revised)

## Status
Accepted — 2026-09-09. Revises the blueprint's original framing of ADR-0005
(Excel as a one-way export / candidate system of record).

## Context
I want to triage and track applications in a spreadsheet — it's the fastest way
to eyeball a list and bulk-edit "applied / outcome / notes". The original design
left the door open to Excel being *the* store, or a one-way dump. Both are wrong:

- A spreadsheet as the source of truth loses every relational guarantee this
  project just built (constraints, the write-ownership invariant, migrations).
- A one-way export means every manual edit is thrown away on the next export —
  you'd re-type `applied=YES` after every ingestion run.

## Decision
**PostgreSQL is the single source of truth. Excel is a supported *input* for the
handful of fields I own, applied through an explicit, reviewed import.**

- **Export** (`GET /exports/xlsx`, `ExportService.export_xlsx`) writes one row per
  job: read-only context (`Title`, `Company`, `URL`) + the editable application
  fields (`Applied`, `Applied At`, `Networking`, `Outcome`, `Application URL`,
  `Notes`) + two **hidden** columns, `job_id` and `revision`. Column layout is one
  place: `app/exports/layout.py`.
- **Import** (`POST /exports/import`, `ExportService.import_xlsx`):
  - **keyed on the hidden `job_id`** — never on title/company text.
  - **field-scoped** — only the `editable` columns are read back; a changed
    `Title` or `URL` cell is ignored. The write goes through `ApplicationPatch`
    (`extra="forbid"`), so a canonical `jobs` field is structurally unwritable
    (ADR-0011).
  - **never creates a job and never deletes anything.** An unknown `job_id` is an
    `error` row, reported, skipped.
  - `xlsx` is uploaded as the **raw request body** (`curl --data-binary @f.xlsx`) —
    no `python-multipart` dependency for a single-file, single-user upload.
- The staleness guard and dry-run default are ADR-0010.

## Consequences
- The database keeps all its guarantees; the spreadsheet is a view + a batch-edit
  form, nothing more.
- `app/exports/` is pure (`import-linter`: no `db/`, `models/`, `services/`).
  `excel.py` does `.xlsx <-> rows` with openpyxl and no business logic; the
  reconcile lives in `ExportService`.
- Re-importing an untouched export is a no-op — every row reports `unchanged`.
- Adding a column later is a `layout.py` edit plus deciding `editable=`.
