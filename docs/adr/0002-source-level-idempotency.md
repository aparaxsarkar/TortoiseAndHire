# ADR-0002: Source-level idempotency

## Status
Accepted — 2026-09-07

## Context
The product's primary requirement: ingesting the same posting from the same source
repeatedly must produce exactly one database record. This has to hold even under
concurrent ingestion runs, and it must be the *database's* guarantee, not something
application code remembers to do.

Providers differ in what they expose. Greenhouse, Lever, and Ashby give a stable
per-posting id; some feeds and some parse paths yield nothing usable but a URL. So
`(source_id, source_job_id)` cannot be the sole uniqueness key — `source_job_id` is
nullable, and in Postgres two NULLs do not collide, so a plain unique constraint on it
would let duplicates through whenever the id is absent.

## Decision
`source_postings` (and the reject ledger `filtered_postings`) carry a materialised
**`dedup_key TEXT NOT NULL`**, set on write to `coalesce(source_job_id, canonical_url)`.

The idempotency guarantee is one constraint that always applies:

```
CONSTRAINT uq_source_postings_source_id_dedup_key  UNIQUE (source_id, dedup_key)
```

Backed up, when the provider *does* give an id, by a partial unique index:

```
CREATE UNIQUE INDEX uq_source_postings_source_job_id_partial
    ON source_postings (source_id, source_job_id)
    WHERE source_job_id IS NOT NULL;
```

Ingestion persists with `INSERT ... ON CONFLICT (source_id, dedup_key) DO UPDATE`. Insert
vs. update is told apart by the `xmax = 0` trick; a `content_hash` column (a hash of the
normalised fields) then distinguishes a real change from a no-op re-ingest, so
re-scanning a source only advances timestamps and never churns `updated` counts.

Canonicalising the URL (stripping tracking params, normalising case/trailing slash) is
`app/deduplication/url_canonical.py`'s job so the fallback key is stable.

## Consequences
- Re-running any ingestion is safe by construction; the headline integration test
  double-ingests a fixture set and asserts identical row counts and an unchanged
  `first_ingested_at`.
- Two concurrent runs for the same source can at worst both attempt the insert; the
  constraint makes one of them an update. (A per-source advisory lock, added with the
  runner, also prevents the overlap in the first place.)
- Cross-source deduplication is explicitly *not* covered here — that is a separate,
  suggestion-only concern (ADR-0007, if built).
- The `dedup_key` is derived data. Nothing else should write it; a repository helper
  computes it from the identity.
