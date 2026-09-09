# ADR-0010: Excel import — dry-run by default, revision-guarded

## Status
Accepted — 2026-09-09

## Context
The Excel import (ADR-0005) writes to my private `applications` data. Two things
can go wrong with a spreadsheet edited by hand over days:

1. **A blind commit.** You meant to change three rows, a stray edit changed a
   fourth, and you don't notice until later.
2. **A stale write.** You exported on Monday, the record changed (another edit, a
   future admin UI) on Wednesday, and importing Monday's sheet on Friday silently
   reverts Wednesday's change.

## Decision

**Dry-run by default; a hidden `revision` column is a per-row optimistic lock.**

- **`commit` is `false` unless asked.** `POST /exports/import` (no `?commit=true`)
  reads nothing back into the database. It returns an `ImportReport`: per row an
  `action` (`created` / `updated` / `unchanged` / `conflict` / `error`), the exact
  field-level `changes` a commit *would* make, and `counts`. You read it, then
  re-POST with `?commit=true`.
- **The `revision` guard.** The export stamps each row with the live
  `applications.revision` (`0` if there's no row yet). On import, if the sheet's
  `revision` doesn't equal the current one, that row is a **`conflict`**: it is
  skipped (even under `commit=true`), reported with both numbers, and the live
  row is left exactly as it was. Fix is to re-export and redo that row.
- **Every applied change bumps `revision` and sets `updated_via = "excel_import"`**
  — through the same `write_application` helper the API `PATCH` uses, so the two
  paths can't diverge. A brand-new row lands at `revision = 1`.
- **A commit is atomic and audited.** All applied rows commit in one transaction
  (a mid-loop failure rolls the whole import back), and the commit writes one
  `application_import_runs` row: `filename`, `committed=true`, the `counts`, and
  the full per-row `report` as JSONB. That table has no FK — pruning it cascades
  nowhere.
- **Bad input is a row, not a 500.** An unknown `job_id`, an out-of-vocabulary
  `Networking`/`Outcome`, an unparseable `Applied`/`Applied At` cell → an `error`
  row with a message. Only a structurally broken file (not an `.xlsx`, missing the
  `job_id` column) is a 422 for the whole request.

## Consequences
- You always see what an import will do before it does it, and can't clobber a
  newer edit by importing an old sheet.
- The `conflict` path is integration-tested: export, mutate the DB row, import the
  stale sheet under `commit=true`, assert the row is untouched.
- `revision` is monotonic per application and is the same number the API `PATCH`
  advances — one meaning, two writers.
