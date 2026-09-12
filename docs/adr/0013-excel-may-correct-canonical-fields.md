# ADR-0013: Excel import may also correct Title/Company/URL, flagged separately

## Status
Accepted — 2026-09-12. Narrows ADR-0011's second rule for one path only; see the
addendums on ADR-0005, ADR-0010, and ADR-0011.

## Context
Ingestion sometimes gets a field wrong - a title truncated oddly, a company name
parsed from the wrong HTML node, a URL that's since redirected. Until now the
only fix was to wait for a re-scrape to happen to correct itself, which it often
won't (an unchanged upstream posting never gets touched again — ADR-0002). The
Excel round-trip is already the reviewed, human-in-the-loop path for editing a
job record by hand; the request was to let it fix these three fields too,
**with a loud, distinct signal** so a fix doesn't get mistaken for routine status
housekeeping - and to still block nothing, since the existing dry-run already
requires reading the diff before approving it.

This directly narrows ADR-0011's rule: *"Application writes ... must never
modify a canonical `jobs` / `source_postings` field."* That rule stands for
every other write path. This ADR carves out one path, three fields, one
mechanism.

## Decision

**`Title`, `Company`, and `URL` are now editable in the exported sheet
(`app/exports/layout.py`: `canonical=True`). A change to any of them is reported
and applied through a separate channel from ordinary application-field edits -
never folded into an "updated" that could hide inside a routine status change.**

- **Separate reporting.** `ImportRowResult.canonical_changes` (parallel to the
  existing `changes`) and `ImportReport.canonical_change_count` at the top level.
  `action` (`created`/`updated`/`unchanged`/`conflict`/`error`) keeps its
  existing meaning - it describes only the `applications` row. A row can be
  `"unchanged"` (no application edit) while still carrying a `canonical_changes`
  entry that *will* be applied on commit; the two are reported and counted
  independently on purpose, so a canonical edit is never buried inside (or
  mistaken for) an application-field summary.
- **Same dry-run / commit gate as everything else** (ADR-0010) - nothing new to
  approve, no new endpoint. `?commit=true` applies both kinds of change in the
  same pass, atomically, in the same `application_import_runs` audit row.
- **Title**: writes `jobs.title` and recomputes `jobs.normalized_title`
  (`services.ingestion.normalize_name`, the same normalizer ingestion uses).
- **Company reassigns, never renames.** Editing "Company" resolves-or-creates a
  `Company` row by the new name (`CompanyRepository.get_or_create` - the exact
  path ingestion already uses) and points `jobs.company_id` at it. It does
  **not** rename the existing `companies` row in place. Renaming in place would
  silently relabel every other job from that employer; reassigning changes
  only the one row you're looking at. If you're fixing a genuine company-wide
  misspelling, do that as a separate, deliberate operation (direct SQL / a
  future admin tool), not as a side effect of fixing one job.
- **URL applies only when the job has exactly one linked `source_posting`.**
  With zero or several, the edit is reported as ignored (`message`, not an
  error) rather than guessing which posting you meant - `jobs`/`source_postings`
  is modeled 1:N (ADR-0003); the MVP is effectively 1:1, but the code doesn't
  assume it. Applying it writes `source_postings.canonical_url` **and nothing
  else** - `dedup_key` is never touched, since it's derived data owned by
  ingestion's identity logic (ADR-0002); if it were also overwritten, a future
  re-ingest of the same untouched posting could recompute a *different*
  `dedup_key` and silently create a duplicate `source_postings` row instead of
  recognizing it as already-seen.
- **Blank means "leave as-is," never "clear it."** All three columns back
  `NOT NULL` database columns; a cell someone deleted by mistake must not
  blank out the record. `app/exports/excel.py::_as_url` also rejects a
  non-blank, non-http(s) value outright (a whole-row `error`, same as any other
  malformed cell) rather than writing garbage into `canonical_url`.

## Consequences
- **No revision lock on canonical fields**, unlike `applications.revision`
  (ADR-0010). The diff is always against whatever's live in the database at
  import time, same as it always was for application fields before the guard
  was added - accepted as a known gap, not a silent one. If this bites in
  practice (concurrent edits crossing in transit), the fix is the same shape as
  ADR-0010's: a revision-like counter on `jobs`.
- **A later real re-ingestion can still overwrite a manual correction.** If the
  source posting is genuinely unchanged, `content_hash` matches and ingestion's
  sink never rewrites the job row (ADR-0002) - your fix survives. If the
  underlying posting actually changes upstream, the next scrape *will* rewrite
  `title`/`location`/etc. from the fresh content, silently reverting the Excel
  fix. This project has no per-field "user pinned this" lock; adding one is
  future work if it turns out to matter.
- `import-linter`'s boundaries are unchanged: `app/exports/` is still pure (no
  `db`/`models`/`services`), and `app/services/exports.py` is the only caller of
  the new write path - the API `PATCH` (`app/services/applications.py`) still
  cannot touch a canonical field; `ApplicationPatch` still has `extra="forbid"`
  over exactly the seven user-owned fields. Ingestion's prohibition on touching
  `applications` (ADR-0011 rule 1) is entirely untouched by this ADR.
- New repository method: `SourcePostingRepository.list_for_job` (read-only,
  ordered the same way `JobRepository.source_links_for` is, so "the first
  posting" means the same thing at export and at import).
