# ADR-0003: Canonical job vs. source posting are separate tables

## Status
Accepted — 2026-09-07

## Context
A posting exists twice: as the raw thing a source served us, and as the canonical
"role at a company" a person cares about. For the MVP these are effectively 1:1 — each
`source_posting` maps to one `job`. The question is whether to collapse them into one
table now and split later, or model the split from the start.

## Decision
Two tables, `jobs` (canonical) and `source_postings` (per-source raw), with
`source_postings.job_id -> jobs.id` as **1:N** (a job may have many source postings).

- `jobs` holds the normalised, deduplicated fields plus lifecycle columns
  (`first_seen_at`, `last_seen_at`, `status`) and is what the API, search, and Excel
  export read.
- `source_postings` holds `raw_payload`, `content_hash`, the dedup key (ADR-0002), and
  per-source ingest timestamps. It is the audit trail of "what each source told us and
  when".
- `companies` is its own table; `jobs.company_id` is a FK, resolved via
  `get_or_create(normalized_name)`.

## Consequences
- The MVP writes exactly one `source_posting` per `job`, so the relation is 1:1 in
  practice. Modelling it as 1:N costs one extra table and a resolve-or-create step in the
  persist stage now.
- It buys the ability to later attach cross-source linking (the same role posted to two
  ATSes) by pointing a second `source_posting` at an existing `job` — with **no
  migration**, because the schema already allows it.
- Search, export, and application tracking all key off `jobs.id`, so they are unaffected
  by how many sources a job came from.
- `filtered_postings` deliberately has no `job_id` — a rejected posting never becomes a
  job (ADR-0009).
