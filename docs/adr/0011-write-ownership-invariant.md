# ADR-0011: Write-ownership invariant

## Status
Accepted — 2026-09-07

## Context
Job discovery is system-owned; application tracking is user-owned. If an ingestion run
could touch an `applications` row, a scheduled scrape at 3pm could silently wipe out the
`applied` / `outcome` edits made that morning. "They're different tables" is an
observation, not a guarantee — an accidental cascade, a stray trigger, or a repository
method that does too much would all break it just as effectively.

## Decision
The invariant, stated both ways:

- **Ingestion** may insert or update `companies`, `jobs`, `source_postings`,
  `filtered_postings`, `ingestion_runs`, `ingestion_errors` — and must **never** create,
  update, or delete an `applications` row.
- **Application writes** (the API `PATCH`, the Excel import) may insert or update
  `applications` and `application_import_runs` — and must **never** modify a canonical
  `jobs` / `source_postings` field.

Enforced by the implementation, not assumed:

1. **Repository separation.** Only `ApplicationRepository` writes `applications`, and it is
   never wired into the ingestion path. `import-linter` forbids `app/ingestion/` from
   importing the applications model.
2. **`ON DELETE RESTRICT`, never `CASCADE`.** `applications.job_id -> jobs` is `RESTRICT`,
   so a job with an application cannot be deleted, so no "delete job -> cascade-drop
   application" path exists. Every FK in the schema is `RESTRICT` except one deliberate
   exception: `ingestion_errors.run_id -> ingestion_runs` is `CASCADE` (an error row has
   no meaning without its run). `source_postings.last_run_id` is `SET NULL`.
3. **Zero database triggers.** Every write is explicit application code plus `ON CONFLICT`.
   A schema test asserts `pg_trigger` (non-internal) is empty.
4. **Typed patch objects** (from day 9): `ApplicationPatch` carries only user-owned
   fields; the ingestion write struct carries only canonical fields. The wrong write is
   unrepresentable at the seam.
5. **Invariant integration tests**: deleting a tracked job raises `ForeignKeyViolation`;
   (from day 6+) re-ingesting a changed posting leaves the linked `applications` row
   byte-identical including `revision` and `updated_at`.

Stretch: two least-privilege Postgres roles (`tortoiseandhire_ingest` /
`tortoiseandhire_app`) on separate connections, so the boundary holds at the database even
against a bug.

## Consequences
- The user's manual application state is safe from every automated write path by
  construction, and it is checked in CI, not left to discipline.
- Deleting a job is deliberately hard. That is the point — jobs are retained (`status` is
  set to `closed`, not `DELETE`d), so `RESTRICT` never actually blocks normal operation.
- `updated_at` is maintained by SQLAlchemy's `onupdate`, not a trigger — consistent with
  rule 3.
