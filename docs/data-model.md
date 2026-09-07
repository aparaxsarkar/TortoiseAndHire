# Data model

The schema as of the day-3 initial migration (`migrations/versions/0001_initial_schema.py`).
The ORM models are in `app/models/`; the enums and their `CHECK` helper are in
`app/models/enums.py`. Constraint names follow the convention in `app/db/base.py`, so
`alembic check` (models == migration) and the schema tests can rely on them.

## Entities

```mermaid
erDiagram
    COMPANIES ||--o{ JOBS : employs
    SOURCES ||--o{ SOURCE_POSTINGS : originates
    SOURCES ||--o{ FILTERED_POSTINGS : "screened out"
    SOURCES ||--o{ INGESTION_RUNS : "scanned by"
    JOBS ||--o{ SOURCE_POSTINGS : "seen as"
    JOBS ||--|| APPLICATIONS : "tracked by"
    INGESTION_RUNS ||--o{ INGESTION_ERRORS : records
    INGESTION_RUNS |o--o{ SOURCE_POSTINGS : "last touched"
    APPLICATION_IMPORT_RUNS

    COMPANIES {
        uuid id PK
        text normalized_name UK
        text name
        text domain "nullable"
    }
    SOURCES {
        smallint id PK
        text slug UK "greenhouse | lever | ashby | workday"
        text display_name
    }
    JOBS {
        uuid id PK
        uuid company_id FK "-> companies, RESTRICT"
        text title
        text normalized_title
        timestamptz posted_at "nullable"
        timestamptz first_seen_at
        timestamptz last_seen_at
        text status "CHECK open|closed|unknown"
    }
    SOURCE_POSTINGS {
        uuid id PK
        smallint source_id FK "-> sources, RESTRICT"
        uuid job_id FK "-> jobs, RESTRICT"
        text source_job_id "nullable"
        text canonical_url
        text dedup_key "= coalesce(source_job_id, canonical_url)"
        jsonb raw_payload
        text content_hash
        uuid last_run_id FK "-> ingestion_runs, SET NULL, nullable"
    }
    FILTERED_POSTINGS {
        uuid id PK
        smallint source_id FK "-> sources, RESTRICT"
        text dedup_key
        jsonb reasons
        text ruleset_version
        jsonb raw_payload "nullable"
    }
    APPLICATIONS {
        uuid id PK
        uuid job_id FK "-> jobs, RESTRICT, UNIQUE (1:1)"
        bool applied
        text networking "CHECK"
        text outcome "CHECK"
        text application_url "nullable, user override"
        int revision "bumped every write"
        text updated_via "CHECK api|admin_ui|excel_import"
    }
    INGESTION_RUNS {
        uuid id PK
        smallint source_id FK "-> sources, RESTRICT"
        text trigger "CHECK manual_api|cli|scheduled"
        text status "CHECK running|success|partial|failed|skipped"
        jsonb stats
        timestamptz started_at
        timestamptz finished_at "nullable"
    }
    INGESTION_ERRORS {
        uuid id PK
        uuid run_id FK "-> ingestion_runs, CASCADE"
        text stage "CHECK fetch|parse|validate|identity|relevance|persist"
        text error_type
        text message
    }
    APPLICATION_IMPORT_RUNS {
        uuid id PK
        text filename
        bool committed
        jsonb stats
        jsonb report
    }
```

## Load-bearing constraints

| Constraint | Table | Purpose |
|---|---|---|
| `uq_source_postings_source_id_dedup_key` | `source_postings` | ADR-0002 idempotency anchor |
| `uq_source_postings_source_job_id_partial` | `source_postings` | partial `UNIQUE (source_id, source_job_id) WHERE source_job_id IS NOT NULL` — backs up the anchor when the provider gives an id |
| `uq_filtered_postings_source_id_dedup_key` | `filtered_postings` | same dedup discipline for the reject ledger (ADR-0009) |
| `uq_applications_job_id` | `applications` | 1:1 with `jobs` |
| `fk_applications_job_id_jobs` (`ON DELETE RESTRICT`) | `applications` | ADR-0011 — a tracked job can't be deleted |
| `fk_ingestion_errors_run_id_ingestion_runs` (`ON DELETE CASCADE`) | `ingestion_errors` | the one intentional cascade |
| every `ck_*` | various | enum values enforced in the DB, sourced from `app/models/enums.py` |
| *(none)* | — | **zero triggers** — asserted by a schema test (ADR-0011) |

## Conventions

- **UUID primary keys**, generated app-side (`default=uuid.uuid4`) so ORM objects have an
  id before flush. `sources` is the exception: a small `SMALLINT` identity, since it is a
  fixed 4-row lookup seeded by `scripts/seed_sources.py`.
- **`created_at` / `updated_at`** via `CreatedAtMixin` / `TimestampMixin`;
  `server_default now()`, and `updated_at` bumped by SQLAlchemy `onupdate` (not a trigger).
- **Timestamps** are `TIMESTAMP WITH TIME ZONE`.
- The **full-text (GIN) index** for job search is deliberately *not* here — it serves the
  `/jobs?q=` endpoint and lands with search (day 8).
