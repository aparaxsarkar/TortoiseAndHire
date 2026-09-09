# ADR-0001: Record architecture decisions

## Status
Accepted — 2026-09-04

## Context
TortoiseAndHire's design was worked out in full before any code was written: architecture,
repository layout, module boundaries, PostgreSQL schema, ingestion/idempotency design,
relevance filtering, API design, Excel export/import, deployment, CI/CD and testing plan,
and a 2-week MVP schedule. That design lives as a published reference:

> **TortoiseAndHire Blueprint** — https://claude.ai/code/artifact/b8403e88-6927-4187-8c24-08c9174e92ee

Eleven decisions from that process are locked and are recorded as their own ADRs
(0002–0011, each added the day its code lands, per the build plan below) plus the
third-party reuse audit (ADR-0012, added immediately since that decision is already made).
Without a written record, later contributors — including a future me — would have to
reverse-engineer *why* a constraint or boundary exists from the code alone.

## Decision
Use lightweight architecture decision records (ADRs), one Markdown file per decision, in
`docs/adr/`, numbered sequentially, using this file's structure (Status / Context / Decision
/ Consequences). An ADR is never edited to reverse a decision — a later ADR supersedes an
earlier one and says so explicitly.

`docs/architecture.md` records the *current shape* of the system (what exists, sections
filled in as code lands); ADRs record the *why* behind each locked decision, once. Neither
duplicates the full design blueprint — both point back to it and to each other rather than
re-explaining it.

### Build plan (from the blueprint's §11 MVP schedule)

Each day: identify the files → smallest coherent change → tests → run them → verify the
`import-linter` boundary → update `docs/architecture.md` if the shape changed → open the
day's ADR if a new locked decision landed.

| Day | Focus | ADR |
|---|---|---|
| 1 ✓ | Repo harness: `pyproject.toml`, `docker-compose.yml`, `Dockerfile`, `.env.example`, `Makefile`, pre-commit, empty `app/` packages, `ci.yml` (lint), import-linter contracts | **0001** (this file), **0012** |
| 2 ✓ | `core/`: config, logging, retry, rate-limit, observability; `main.py` + `/health`; CI `test` job | — (`core/retry` is generic infra; the idempotency decision has no code here yet) |
| 3 ✓ | DB layer: `db/base`, `session`, all `models/`, first Alembic migration; `/health/ready`; CI Postgres service + migration round-trip + `alembic check` | **0002** (idempotency anchor), **0003** (canonical vs source-posting split), **0011** (write-ownership: FK `RESTRICT`, no triggers) |
| 4 ✓ | `schemas/canonical`; `deduplication/` (url_canonical, identity, content_hash); `discovery/` (ruleset, experience, rules) + `config/discovery.yml`; repositories (companies get_or_create, source_postings/filtered_postings upsert, sources, jobs); CI coverage gate ≥95% on the pure core | **0009** (relevance filter before persistence) |
| 5 ✓ | `sources/`: `JobSource` protocol + `BaseSource`, shared async `http` client, `SourceError` taxonomy, HTML→text, `registry`; Greenhouse + Lever adapters; `respx`-mocked unit tests + opt-in `@live` smoke tests | **0004** (adapter boundary: fetch/parse only, no DB) |
| 6 ✓ | `ingestion/`: `pipeline.prepare`, `IngestionRunner`, `results`, and the three ORM-free ports; `services/ingestion.py` binds them to repositories (SAVEPOINT isolation, `pg_try_advisory_xact_lock`); new import-linter contract *"ingestion/ is ORM-free"*; coverage gate extended to `app/ingestion/*` | 0004, 0009, 0011 (wired) |
| 7 ✓ | `services/`: `IngestionService` (`run_source` / `run_all` — resolve adapter, own the transaction, map to DTOs); `JobService.search` / `.get`; `schemas/jobs` + `schemas/ingestion` DTOs; `JobRepository.search` (filters + pagination, no N+1); `aclose()` added to the `JobSource` protocol | — (wires 0004/0009/0011) |
| 8 ✓ | API I: `routes/jobs` (public, redacted) + `routes/ingestion` (token); `api/deps` (`require_token`, providers, query parsing); `api/errors` (RFC 7807 problem+json for every path); `TortoiseError` carries `http_status`/`http_title`; `JobService` gets its own `session_factory` so `api/` never imports `db/` | **0008** (server-side-only bearer token) |
| 9 ✓ | `ApplicationService` + `GET`/`PATCH /jobs/{id}/application` (token); `app/exports/` (pure `layout` + `excel` read/write, openpyxl); `ExportService` + `GET /exports/xlsx` + `POST /exports/import` (raw body, dry-run default, `revision` guard, `application_import_runs` audit); `write_application` is the single mutation path | **0005** (revised — Excel is round-trip input), **0010** (dry-run + revision guard) |
| 10 ✓ | Deploy: `docker/Dockerfile` (non-root, carries `config/` + `scripts/`) + `.dockerignore` + `render.yaml`; `scripts/seed_sources` + `scripts/run_ingestion` (mypy-strict + ruff); `.github/workflows/ingest.yml` (6-hourly, hits Neon directly) + `nightly-live.yml`; `GET /metrics` (token); `config/sources.yml`; `docs/runbook.md` | **0006** (Neon + Render + Actions cron) |

**MVP build plan complete.** Post-MVP work extends existing ADRs rather than adding new ones:

| Extension | Notes |
|---|---|
| Ashby + Workday adapters (2026-09-11) | Same `JobSource` contract; `HttpClient` gained `post_json` for Workday's POST list endpoint; Workday target is `tenant:shard:site`. See the ADR-0004 addendum. |

Still deferred: cross-source dedup suggestions (would get ADR-0007), a minimal React frontend,
`GET /sources`.

## Consequences
- Every non-obvious constraint in the code (a `RESTRICT` instead of `CASCADE`, a filter that
  runs before persistence instead of after, a token that never reaches a client) has a
  written reason someone can find in under a minute.
- `docs/architecture.md` can be trusted as "what exists today" without re-deriving it from a
  git log, because it's updated in the same change that alters the shape it describes.
- The ADR set is a flat, growing list — no renumbering, no silent edits. A decision that
  changes gets a new ADR that supersedes the old one.
