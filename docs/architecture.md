# TortoiseAndHire Architecture

This is the repo-resident reference for TortoiseAndHire's design. It records *what the
system looks like*; the *why* behind each locked decision lives in
[`docs/adr/`](adr/). This document grows alongside the code — each section is
filled in or corrected on the day the code it describes is written, per the
build plan in [ADR-0001](adr/0001-record-architecture-decisions.md).

## 1. Architecture overview

TortoiseAndHire is a single deployable Python service. Control flows top-down through
five layers; imports are only ever allowed to point downward. The one
deliberate inversion is at the ingestion → persistence seam: the
`IngestionRunner` writes through a narrow `SourcePostingSink` port (a
`Protocol`), so orchestration logic can be unit-tested with an in-memory fake
and never imports the ORM.

```
app/api            HTTP: routing, request/response schemas, auth, error mapping
app/services        business logic; wires adapters + repositories + the runner; owns transactions
app/ingestion       run orchestration: retries, rate-limit, relevance gate, partial failure
app/deduplication   deterministic source-identity key + URL canonicalization — pure
app/discovery       deterministic relevance filter — pure, config-driven
app/exports         Excel write + read (round-trip) — no DB
app/db/repositories persistence operations only — no business rules
app/models          SQLAlchemy ORM — persistence shape only
app/core            config, logging, retry, rate-limit, observability — cross-cutting, imported by
                    every layer, imports nothing from app/
app/sources         fetch/parse/normalize per ATS — no DB access, no business logic
```

Two runtime entry points exist, both landing in `services/`: the HTTP API
(FastAPI) and a thin CLI / scheduled trigger. Nothing reaches the database
except the repository sublayer. A deterministic **relevance filter**
(`app/discovery`) is a first-class pipeline stage between normalization and
persistence, not an AI-layer add-on — see §6.

## 2. Repository tree

See the top-level [README](../README.md#repository-layout) for the annotated
tree. Full file-by-file layout (as each file is added):

```
TortoiseAndHire/
├── app/
│   ├── main.py                  FastAPI app factory, middleware, router registration
│   ├── api/
│   │   ├── deps.py              DI: get_session, auth, service providers
│   │   ├── errors.py            exception handlers → RFC 7807 problem+json
│   │   └── routes/              health · jobs · applications · ingestion · exports · discovery · sources
│   ├── core/
│   │   ├── config.py            Settings (pydantic-settings), env-only
│   │   ├── logging.py           structlog: JSON in prod, key=value in dev
│   │   ├── observability.py     counters/histograms + request-timing middleware + /metrics
│   │   ├── errors.py            domain exception hierarchy
│   │   ├── retry.py             tenacity wrapper: exp backoff + jitter, honors Retry-After
│   │   └── rate_limit.py        token-bucket limiter, per source
│   ├── db/
│   │   ├── base.py              DeclarativeBase + constraint naming convention
│   │   ├── session.py           engine, sessionmaker, get_session
│   │   └── repositories/        companies · jobs · source_postings · filtered_postings · applications · ingestion · import_runs
│   ├── models/                  SQLAlchemy ORM — persistence shape only
│   ├── schemas/
│   │   ├── canonical.py         RawPosting, CanonicalPosting — the adapter contract
│   │   └── ...                  jobs · applications · ingestion · exports (API DTOs)
│   ├── services/                jobs · applications · ingestion · discovery · exports · imports — business logic
│   ├── sources/
│   │   ├── base.py              JobSource Protocol, SourceQuery, SourceError hierarchy
│   │   ├── registry.py          slug → adapter factory
│   │   ├── http.py              shared async httpx client wrapper
│   │   └── greenhouse.py · lever.py · ashby.py · workday.py
│   ├── ingestion/
│   │   ├── runner.py            IngestionRunner — orchestration, retries, partial failure
│   │   ├── pipeline.py          normalize → validate → identity → relevance steps
│   │   └── results.py           IngestionRunResult, PostingOutcome enums
│   ├── deduplication/
│   │   ├── identity.py          deterministic (source, source_job_id | url) key
│   │   ├── url_canonical.py     URL canonicalization rules
│   │   └── suggestions.py       optional probabilistic cross-source matcher (stretch)
│   ├── discovery/
│   │   ├── ruleset.py           Ruleset model + loader for config/discovery.yml (version-stamped)
│   │   ├── rules.py             evaluate(posting, ruleset) → RelevanceVerdict — deterministic, pure
│   │   └── experience.py        parse "5+ years" / "3-5 years" / "min 2 years" → min_years
│   └── exports/
│       ├── layout.py            the 9 visible columns + hidden job_id / revision
│       └── excel.py             ExcelExporter.write + .read — openpyxl, no DB
├── tests/                       unit · integration · api · fixtures
├── migrations/                  Alembic (env.py + versions/)
├── scripts/                     seed_sources · run_ingestion · export_xlsx · import_applications · reevaluate_filtered
├── config/discovery.yml         target roles / levels / exclusions — versioned, checked in, not a secret
├── docs/
│   ├── architecture.md          this file
│   ├── data-model.md            written alongside the DB layer (day 3)
│   ├── runbook.md               written alongside deployment (day 10)
│   ├── adr/                     0001..0011 decision records
│   └── reference/               dated third-party reference notes (ADR-0012)
├── frontend/                    optional minimal React (Vite + TS) — stretch
├── .github/workflows/           ci.yml · deploy.yml · ingest.yml · nightly-live.yml (added as each becomes real)
├── docker/Dockerfile · docker-compose.yml
├── pyproject.toml · alembic.ini · Makefile
├── .env.example · .pre-commit-config.yaml
└── README.md
```

## 3. Module rules & boundaries

| Module | Owns | May import | Must NOT import |
|---|---|---|---|
| `core/` | Config, logging, retry, rate-limit, metrics, base errors | stdlib, third-party infra libs | any other `app/` package |
| `schemas/` | Pydantic models: canonical posting + API DTOs | `core/`, pydantic | `models/`, `db/`, `sources/`, SQLAlchemy |
| `sources/` | Fetch, parse, normalize → `CanonicalPosting` | `schemas/canonical`, `core/` (http, retry, rate_limit, errors) | `db/`, `models/`, `services/`, `ingestion/`, `api/`, SQLAlchemy |
| `deduplication/` | Deterministic identity key; URL canonicalization; (stretch) match scoring | `schemas/canonical`, stdlib | `db/`, `models/`, `services/`, `api/` |
| `discovery/` | Deterministic relevance filter: target-function / seniority / experience match → keep or reject + reason | `schemas/canonical`, `core/config`, stdlib | `db/`, `models/`, `services/`, `ingestion/`, `api/`, SQLAlchemy |
| `models/` | ORM table definitions, constraints, indexes | `db/base`, SQLAlchemy | `services/`, `api/`, `sources/`, `ingestion/` |
| `db/repositories/` | CRUD, queries, upsert — *no business rules* | `models/`, `db/session`, `schemas/`, SQLAlchemy | `services/`, `api/`, `sources/`, `ingestion/` |
| `ingestion/` | Run orchestration: retries, rate-limit, relevance gate, partial failure, run records | `sources/`, `deduplication/`, `discovery/`, `schemas/`, `core/`, the `SourcePostingSink` / `FilteredPostingSink` ports | `api/`, concrete `models/` / ORM sessions |
| `services/` | Business logic; wires adapters + repos + runner; owns transactions | `db/repositories/`, `ingestion/`, `deduplication/`, `discovery/`, `exports/`, `sources/registry`, `schemas/`, `core/` | `api/` |
| `exports/` | Row data ↔ `.xlsx` bytes: write the export, parse an upload | `schemas/exports`, openpyxl | `db/`, `models/`, `services/` |
| `api/` | HTTP: routing, request/response schemas, auth, error mapping | `services/`, `schemas/`, `core/` | `db/repositories/`, `sources/`, `ingestion/` internals, raw SQL |

**Enforcement** — not aspirational, checked in CI (`make imports`, wired into `.github/workflows/ci.yml`'s `lint` job):

- `import-linter` — layer contracts declared in `pyproject.toml` under `[tool.importlinter]`, mirroring the table above. `lint-imports` fails the build on a violation.
- `mypy --strict` on `app/` — the `Protocol` seams (`JobSource`, `SourcePostingSink`, `FilteredPostingSink`) are only meaningful if types are checked.
- **Write-ownership** (ADR-0011) — `import-linter` forbids `app/ingestion/` and the canonical repos from importing the `applications` model; a schema test (added with the DB layer) asserts `pg_trigger` is empty and `applications → jobs` is `ON DELETE RESTRICT`.

## 4. Interfaces

Defined in full once `schemas/canonical.py`, `sources/base.py`, `deduplication/identity.py`,
`discovery/rules.py`, and the repository/service signatures land (days 4–9). The contracts
are fixed by the design and summarized here as they're implemented; see the ADRs for the
reasoning behind each one (ADR-0002 idempotency, ADR-0009 relevance, ADR-0011 write-ownership).

## 5. Schema & ERD

Written alongside the DB layer (day 3) as `docs/data-model.md`, with the full ERD and the
`UNIQUE (source_id, dedup_key)` idempotency-anchor rationale (ADR-0002). Placeholder removed
once that file exists — do not duplicate the schema in two places.

## 6. Ingestion, relevance & idempotency

Pipeline: `fetch → normalize → identify → relevance filter → idempotent persist → run log`.

- **Idempotency anchor (ADR-0002):** `source_postings.dedup_key = coalesce(source_job_id, canonical_url)`, `NOT NULL`, `UNIQUE (source_id, dedup_key)`, plus a partial unique index on `(source_id, source_job_id) WHERE source_job_id IS NOT NULL`. `INSERT … ON CONFLICT … DO UPDATE` classifies inserted / updated / unchanged via `xmax = 0` + `content_hash` comparison.
- **Relevance filter (ADR-0009):** a core pipeline stage, not an AI-layer add-on. Deterministic `evaluate(posting, ruleset)` combining title function-match + title-only seniority tokens + parsed minimum experience — never a body substring scan. Rejects go to `filtered_postings` (its own `(source_id, dedup_key)` uniqueness, no FK into `jobs`) and never reach the `jobs` table. Bias: keep on ambiguity, marked `weak`.
- **Write-ownership invariant (ADR-0011):** ingestion may insert/update `companies`, `jobs`, `source_postings`, `filtered_postings`, `ingestion_*` — and must never create, update, or delete an `applications` row. Enforced by repository separation, typed patch objects, FK `ON DELETE RESTRICT`, zero database triggers, and integration tests.
- **Reliability:** per-source `pg_advisory_lock` (no overlapping runs), `tenacity` retry with exponential backoff + jitter honoring `Retry-After`, per-source token-bucket rate limiting, per-posting failure isolation (`ingestion_errors`, run continues as `partial`).

## 7. API design

REST under `/api/v1`. Auth (ADR-0008): a single bearer token, **server-side only** — never
shipped to any client. Public reads are redacted (no `application`/`networking`/`notes` keys);
every write, the personal application/networking endpoints, the ingestion trigger, the Excel
import, and exports require the token. Errors are RFC 7807 `application/problem+json`. Full
endpoint table lands in this section once `app/api/routes/` exists (days 8–9).

## 8. Excel export & import

PostgreSQL stays the single source of truth (ADR-0005, revised). Excel is a supported *input*
for the fields I own (`applied`, `networking`, `outcome`, `application_url` override, `notes`),
through an explicit reviewed import — not a live sync (ADR-0010): keyed on a hidden `job_id`
column, field-scoped, dry-run by default, revision-guarded against stale writes, never creating
or deleting anything. Full column mapping and mechanics land here once `app/exports/` exists
(day 9).

## 9. Deployment

Neon (Postgres) + Render (API, Docker) + GitHub Actions scheduled workflow (ingestion trigger)
+ Cloudflare Pages (frontend, stretch). All 12-factor: config from env, stateless containers, DB
via `DATABASE_URL`. Detailed in `docs/runbook.md` once deployment is set up (day 10, ADR-0006).

## 10. CI/CD & testing

Target pipeline: lint → test → build → deploy, each job added to `.github/workflows/ci.yml` the
day the code it exercises exists (see ADR-0001's build plan) rather than stubbed ahead of time.
Coverage gates: ≥ 80% on `app/`, ≥ 95% on `deduplication/`, `discovery/`, and `ingestion/` (the
correctness-critical core). See §10 of the design blueprint (linked from ADR-0001) for the full
testing-boundaries table.

## 11. Not used (deliberately)

Celery/Redis, Kafka/RabbitMQ, Kubernetes, Airflow/Dagster/Prefect, Ray/Spark/Dask,
Elasticsearch, a dedicated vector DB, GraphQL, MongoDB, Playwright (for now), managed
auth platforms, Terraform, database triggers, live Excel sync, and per-posting LLM
classification. Each has a one-line reason and a "reconsider when" trigger in the design
blueprint referenced from ADR-0001 — repeating the full table here would drift out of sync
with it, so it isn't duplicated in this file.
