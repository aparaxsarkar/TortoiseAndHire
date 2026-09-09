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
│   │   ├── deps.py              require_token (bearer), service providers, job_filters query parsing
│   │   ├── errors.py            ProblemException + handlers → RFC 7807 application/problem+json
│   │   └── routes/              health · jobs (public) · applications · ingestion · exports · metrics (token)
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
│   │   ├── jobs.py              JobFilters (search input) · JobSummary · JobSearchResult
│   │   ├── ingestion.py         RunRequest · SourceRunResult · IngestionReport · IngestionRunSummary
│   │   ├── applications.py      ApplicationPatch (user-owned fields only) · ApplicationView
│   │   └── exports.py           ExportRow · ImportReport (+ per-row result / change)
│   ├── services/                business logic; owns transactions; returns DTOs, never ORM rows
│   │   ├── ingestion.py         Repository{SourcePostingSink,FilteredPostingSink,RunStore} (ORM half of the seam) + IngestionService
│   │   ├── jobs.py              JobService.search / .get — read-side
│   │   ├── applications.py      ApplicationService (get / patch) + write_application (the one mutation path)
│   │   ├── exports.py           ExportService — snapshot + reconcile the Excel round-trip
│   │   └── health.py            readiness probe
│   ├── sources/
│   │   ├── base.py              JobSource Protocol, SourceQuery, BaseSource lifecycle
│   │   ├── errors.py            SourceError taxonomy (Unavailable · RateLimited · Auth · Payload)
│   │   ├── http.py              shared async httpx wrapper: UA, token bucket, retry, status→error
│   │   ├── _html.py             minimal HTML → plain text (stdlib only)
│   │   ├── registry.py          slug → adapter factory (available() · get_source())
│   │   └── greenhouse.py · lever.py · ashby.py · workday.py
│   ├── ingestion/               ORM-free: persists only through the ports in ports.py
│   │   ├── runner.py            IngestionRunner — advisory lock, retry-around-fetch, relevance gate, partial failure, run tally
│   │   ├── pipeline.py          prepare(raw): parse → identity → relevance → content_hash; PipelineError tags the failing stage
│   │   ├── ports.py             SourcePostingSink · FilteredPostingSink · RunStore Protocols; PersistOutcome
│   │   └── results.py           IngestionRunResult (also the ingestion_runs.stats shape) · PostingError
│   ├── deduplication/
│   │   ├── identity.py          deterministic (source, source_job_id | url) key
│   │   ├── url_canonical.py     URL canonicalization rules
│   │   └── suggestions.py       optional probabilistic cross-source matcher (stretch)
│   ├── discovery/
│   │   ├── ruleset.py           Ruleset model + loader for config/discovery.yml (version-stamped)
│   │   ├── rules.py             evaluate(posting, ruleset) → RelevanceVerdict — deterministic, pure
│   │   └── experience.py        parse "5+ years" / "3-5 years" / "min 2 years" → min_years
│   └── exports/                 pure: no db/ models/ services/ (import-linter)
│       ├── layout.py            the 9 visible columns + hidden job_id / revision; which are editable
│       └── excel.py             write_workbook / read_workbook — openpyxl only, cell coercion, no DB
├── tests/                       unit · integration (needs Postgres) · api · fixtures
├── migrations/                  Alembic (env.py + versions/) — run out of band, never on container start
├── scripts/                     seed_sources · run_ingestion (mypy-strict + ruff, like app/)
├── config/                      discovery.yml (relevance ruleset) · sources.yml (which boards to scan)
├── docs/
│   ├── architecture.md          this file
│   ├── data-model.md            ERD + constraints (day 3)
│   ├── runbook.md               deploy setup, routine ops, incident playbook (day 10)
│   ├── adr/                     0001..0006, 0008..0012 decision records
│   └── reference/               dated third-party reference notes (ADR-0012)
├── .github/workflows/           ci.yml (lint + test) · ingest.yml (6-hourly discovery) · nightly-live.yml
├── docker/Dockerfile            non-root, carries app/ migrations/ config/ scripts/; CMD = uvicorn only
├── docker-compose.yml           local Postgres + API
├── render.yaml                  Render Blueprint (ADR-0006)
├── pyproject.toml · alembic.ini · Makefile · .dockerignore
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
| `ingestion/` | Run orchestration: advisory lock, retry-around-fetch, relevance gate, partial failure, run tally; defines its own `SourcePostingSink` / `FilteredPostingSink` / `RunStore` ports | `sources/`, `deduplication/`, `discovery/`, `schemas/`, `core/` | `db/`, `models/`, `services/`, `api/` (it never sees a session) |
| `services/` | Business logic; wires adapters + repos + runner; owns transactions | `db/repositories/`, `ingestion/`, `deduplication/`, `discovery/`, `exports/`, `sources/registry`, `schemas/`, `core/` | `api/` |
| `exports/` | Row data ↔ `.xlsx` bytes: write the export, parse an upload | `schemas/exports`, openpyxl | `db/`, `models/`, `services/` |
| `api/` | HTTP: routing, request/response schemas, auth, error mapping | `services/`, `schemas/`, `core/` | `db/repositories/`, `sources/`, `ingestion/` internals, raw SQL |

**Enforcement** — not aspirational, checked in CI (`make imports`, wired into `.github/workflows/ci.yml`'s `lint` job):

- `import-linter` — 7 contracts declared in `pyproject.toml` under `[tool.importlinter]`, mirroring the table above. `lint-imports` fails the build on a violation. Two are Day-5/6 boundary walls: *"sources/ have no DB access and no business logic"* and *"ingestion/ is ORM-free: it persists only through its ports"* (`app.ingestion` may not import `app.db` / `app.models` / `app.services` / `app.api`).
- `mypy --strict` on `app/` — the `Protocol` seams (`JobSource`, `SourcePostingSink`, `FilteredPostingSink`, `RunStore`) are only meaningful if types are checked.
- **Write-ownership** (ADR-0011) — the ORM-free-`ingestion/` contract above is what makes the seam physical: the runner literally cannot reach `applications`. A schema test (DB layer) also asserts `pg_trigger` is empty and `applications → jobs` is `ON DELETE RESTRICT`, and an integration test double-runs ingestion over a job that has an `applications` row and asserts that row is byte-identical afterwards.

## 4. Interfaces

Defined in full once `schemas/canonical.py`, `sources/base.py`, `deduplication/identity.py`,
`discovery/rules.py`, and the repository/service signatures land (days 4–9). The contracts
are fixed by the design and summarized here as they're implemented; see the ADRs for the
reasoning behind each one (ADR-0002 idempotency, ADR-0009 relevance, ADR-0011 write-ownership).

### `core/` (day 2)

| Symbol | Signature | Notes |
|---|---|---|
| `config.Settings` | `BaseSettings` | Env-var-backed, prefix `TORTOISEANDHIRE_` (except `DATABASE_URL`, unprefixed for PaaS compatibility). |
| `config.get_settings()` | `() -> Settings` | `lru_cache`d; the one place config enters the app. App code never reads `os.environ`. |
| `logging.configure_logging(settings)` | `(Settings) -> None` | Called once in `create_app()`. structlog: console renderer in dev, one JSON object per line in prod. |
| `logging.get_logger(*names)` | `(*str) -> BoundLogger` | Emit key/value events: `log.info("ingestion.run.finished", inserted=17)`. |
| `retry.retry_policy(...)` / `async_retry_policy(...)` | `(...) -> tenacity.Retrying` / `AsyncRetrying` | Callable: `retry_policy(retry_on=X)(fn, *args)`. Exponential backoff + jitter, capped, `reraise=True`. `Retry-After` handling is layered on in `sources/http.py`. |
| `rate_limit.TokenBucket` | `dataclass(rate, capacity, clock=time.monotonic)` | `consume(n) -> bool`, `time_until(n) -> float`, `async acquire(n)`. One bucket per source. `clock` injectable for tests. |
| `observability.metrics` | `Metrics` singleton | `inc(name, **labels)`, `observe(name, value)`, `render_prometheus() -> str`. In-memory; not a metrics backend. |
| `observability.TimingMiddleware` | raw ASGI middleware | One request counter + one duration observation + a structured log line per request. Wired in `create_app()`. |
| `errors.TortoiseError` | `Exception` | Root of the first-party exception hierarchy. |

Entrypoint: `app.main.create_app(settings=None) -> FastAPI`; `app.main:app` is the uvicorn target.
Routes so far: `GET /api/v1/health` (liveness), `GET /api/v1/health/ready` (503 if the DB is
unreachable).

### `schemas/`, `deduplication/`, `discovery/`, `db/repositories/` (day 4)

| Symbol | Signature | Notes |
|---|---|---|
| `schemas.canonical.CanonicalPosting` | pydantic model | The normalised posting; the only thing that leaves `sources/`. `RawPosting` is the pre-parse form. |
| `deduplication.url_canonical.canonicalize_url` | `(str) -> str` | Lowercase scheme/host, drop default port + fragment + tracking params, sort params, trim trailing slash. Deterministic, idempotent. |
| `deduplication.identity.derive` | `(CanonicalPosting) -> PostingIdentity` | `dedup_key = source_job_id or canonicalized_url`; raises `IdentityError` if neither is usable. |
| `deduplication.identity.content_hash` | `(CanonicalPosting) -> str` | SHA-256 over the human-meaningful fields; the change signal for the upsert. Ignores `url` and `source_metadata`. |
| `discovery.ruleset.load_ruleset` | `(path) -> Ruleset` | Parses/validates `config/discovery.yml` (frozen, `extra="forbid"`). No settings dependency. |
| `discovery.experience.parse_min_years` | `(str \| None) -> int \| None` | Lowest required years, or `None` (biased toward `None` = keep). |
| `discovery.rules.evaluate` | `(CanonicalPosting, Ruleset) -> RelevanceVerdict` | `matched`, `strength` (`strong`/`weak`), `reasons[]`, `signals{}`, `ruleset_version`. Function match required; seniority checked in the title only; keep-on-ambiguity. |
| `db.repositories.CompanyRepository.get_or_create` | `(*, normalized_name, name, domain=None) -> Company` | SELECT, else INSERT inside a SAVEPOINT so a lost race falls back to a re-SELECT. |
| `db.repositories.SourcePostingRepository.upsert` | `(...) -> UpsertOutcome` | `INSERT ... ON CONFLICT (source_id, dedup_key) DO UPDATE`; `INSERTED`/`UPDATED`/`UNCHANGED` from `xmax = 0` + prior-`content_hash` compare. |
| `db.repositories.FilteredPostingRepository.upsert` | `(...) -> None` | Same idempotency for the reject ledger. |
| `db.repositories.{SourceRepository, JobRepository}` | small | `get_by_slug`/`list_all`; `add`/`get`. Search lands day 8. |

Repositories take a `Session` in their constructor and hold no other state. They are the
only code that runs queries (import-linter enforces this).

### `sources/` (day 5)

Adapters do exactly two things — fetch a board's feed, parse it into `CanonicalPosting` —
and import only `schemas/canonical` + `core/`. No DB, no relevance, no dedup, no run logic
(ADR-0004; `import-linter` enforces it).

| Symbol | Signature | Notes |
|---|---|---|
| `sources.base.JobSource` | `Protocol` | `slug: ClassVar[str]`; `fetch(SourceQuery) -> AsyncIterator[RawPosting]`; `parse(RawPosting) -> CanonicalPosting`; `async aclose()` (the caller that built the adapter owns its lifecycle — day 7). `runtime_checkable`. |
| `sources.base.SourceQuery` | pydantic model | `targets: list[str]` — per-adapter identifiers: Greenhouse board tokens, Lever account slugs, Ashby board names, Workday `tenant:shard:site`. |
| `sources.base.BaseSource` | class | Shared HTTP lifecycle: `__init__(http=None)`, `_make_http()` (override for per-source rate limit / base URL), `aclose()`, async context manager. |
| `sources.http.HttpClient` | `(*, base_url, rate_limit=None, timeout=20, user_agent=UA, retry_attempts=4, retry_backoff=0.5)` | One `httpx.AsyncClient`; honest UA + `Accept-Language: en-US`; per-source `TokenBucket`; `tenacity` retry on `SourceUnavailable`; `Retry-After` ≤ 30 s honoured once. `get_json(url, *, params=None)` and `post_json(url, *, json_body, params=None)` — both through the same retry / status-mapping path. |
| `sources.errors.SourceError` | `TortoiseError` | Base. `SourceUnavailable` (5xx/timeout — retry), `SourceRateLimited(*, retry_after)` (429), `SourceAuthError` (401/403 — abort run), `SourcePayloadError` (unparseable — skip one). The runner maps each to a pipeline stage (day 6). |
| `sources.registry.available` | `() -> list[str]` | Sorted registered slugs (`["ashby", "greenhouse", "lever", "workday"]`). |
| `sources.registry.get_source` | `(slug: str) -> JobSource` | Factory lookup; unknown slug → `SourceError`. The only path from slug to adapter. |
| `sources.greenhouse.GreenhouseSource` | `slug="greenhouse"` | `boards-api.greenhouse.io/v1/boards/{token}` (+ `/jobs?content=true`). Entity-decodes `content`, derives `remote`/`department` best-effort. |
| `sources.lever.LeverSource` | `slug="lever"` | `api.lever.co/v0/postings/{account}?mode=json`. Uses `descriptionPlain`/`additionalPlain` directly; `workplaceType` → `remote`. |
| `sources.ashby.AshbySource` | `slug="ashby"` | `api.ashbyhq.com/posting-api/job-board/{board}` — one GET, `{apiVersion, jobs:[…]}`. UUID `id`, both description formats, structured `address` → city/region/country. No company name in the feed → derived from the board token. |
| `sources.workday.WorkdaySource` | `slug="workday"` | Target `tenant:shard:site` (or a `wday/cxs` URL). `POST {base}/jobs` (paged, `limit ≤ 20`) for the list, then one `GET {base}{externalPath}` per posting for the description + real `startDate`. A failed detail GET is isolated (posting kept, list-only). Capped at 300 postings/target. |

### `ingestion/` (day 6)

`app/ingestion/` is the orchestration core and never imports a session (ADR-0011); the
repository-backed port implementations are in `app/services/ingestion.py`.

| Symbol | Signature | Notes |
|---|---|---|
| `ingestion.pipeline.prepare` | `(RawPosting, JobSource, Ruleset) -> PreparedPosting` | `parse → derive identity → evaluate relevance → content_hash`. Raises `PipelineError(stage, ...)` on any stage that can't complete. Pure. |
| `ingestion.pipeline.PreparedPosting` | frozen dataclass | `posting`, `identity`, `verdict`, `content_hash`. |
| `ingestion.runner.IngestionRunner` | `dataclass(source, ruleset, posting_sink, filtered_sink, run_store, trigger="scheduled", fetch_retry_attempts=3, fetch_retry_backoff=1.0)` | `await run(SourceQuery) -> IngestionRunResult`. Skips (no run row) if the advisory lock is held; retries `fetch()` on `SourceUnavailable`; routes each posting to a sink; isolates a per-posting failure into `ingestion_errors` and finishes `partial`. |
| `ingestion.results.IngestionRunResult` | dataclass | Per-run tally (`fetched/matched/filtered_out/inserted/updated/unchanged/failed`) + `status` + `errors[]`. `as_stats()` is the `ingestion_runs.stats` JSONB blob. |
| `ingestion.ports.SourcePostingSink` | `Protocol.persist(*, identity, posting, raw_payload, content_hash, run_id) -> PersistOutcome` | May write `companies`/`jobs`/`source_postings`. |
| `ingestion.ports.FilteredPostingSink` | `Protocol.record(*, identity, posting, verdict, raw_payload) -> None` | Writes `filtered_postings` only. |
| `ingestion.ports.RunStore` | `Protocol`: `source_lock(slug) -> ContextManager[bool]`, `start(...)`, `record_error(...)`, `finish(...)` | Owns `ingestion_runs` / `ingestion_errors` + the `pg_try_advisory_xact_lock` per source. |
| `services.ingestion.Repository{SourcePostingSink,FilteredPostingSink,RunStore}` | `(Session, *, source_id)` / `(Session)` | The ORM implementations. Per-posting `SAVEPOINT` for isolation; `content_hash` gate decides whether the `jobs` row is rewritten. |

### `services/` (day 7)

The entry points the API, CLI, and scheduled job all call. They own the transaction and
return schema DTOs — an ORM object never leaves this layer.

| Symbol | Signature | Notes |
|---|---|---|
| `services.ingestion.IngestionService` | `(*, settings=None, session_factory=session_scope, source_factory=get_source, ruleset=None)` | Composes one run. `session_factory` / `source_factory` are injectable seams for tests. |
| `IngestionService.run_source` | `async (slug, *, targets, trigger="scheduled") -> SourceRunResult` | Resolves the adapter, opens one transaction, wires the repository sinks, runs, maps to a DTO. `session_scope` commits a finished run (incl. `partial`); a runner crash rolls back. `aclose()`s the adapter in a `finally`. Raises `SourceError` (unknown slug) / `IngestionSetupError` (slug not in `sources`). |
| `IngestionService.run_all` | `async (*, plan: Mapping[str, Sequence[str]], trigger=...) -> IngestionReport` | One `run_source` per entry; a source that fails outright becomes a `failed` result rather than aborting the batch. |
| `services.jobs.JobService` | `(session)` | Read-side. |
| `JobService.search` | `(JobFilters) -> JobSearchResult` | Filters: `q` (title), `company`, `source` slug, `remote`, `status`; `limit` (1–200) / `offset`. Order: `posted_at desc nulls last`, then `first_seen_at desc`. One count query + one page query + one batch query for source links (no N+1). |
| `JobService.get` | `(uuid) -> JobSummary \| None` | Single job + its company name + source links. |

### `api/` (day 8)

Routes parse a request, call a service, return a DTO. No DB / sources / ingestion imports
(import-linter). See §7 for the endpoint table.

| Symbol | Notes |
|---|---|
| `api.deps.require_token` | `HTTPBearer(auto_error=False)` + `secrets.compare_digest` vs `settings.api_token` → `ProblemException(401)`. Attached router-level on protected groups. |
| `api.deps.get_job_service` / `get_ingestion_service` | Providers; overridden in tests to inject a rolled-back session / fake adapter. |
| `api.deps.job_filters` | Query params → `JobFilters` (bounds enforced by `Query(ge=…, le=…)`). |
| `api.errors.ProblemException` | `(status, title, detail?, type?)` — what a route raises for a deliberate 4xx. |
| `api.errors.install_error_handlers(app)` | Handlers for `ProblemException`, `RequestValidationError` (422), `HTTPException`, `TortoiseError` (uses `exc.http_status`/`http_title`), and `Exception` (500, logged, no leak). |
| `app.main.create_app` | Mounts `health` + `jobs` + `applications` + `ingestion` + `exports` and installs the handlers. |

### `applications/` + `exports/` (day 9)

| Symbol | Notes |
|---|---|
| `services.applications.write_application` | `(session, job_id, ApplicationPatch, *, via) -> (Application, changed)`. The **only** create/mutate path for `applications` (ADR-0011); the API `PATCH` and the Excel import both call it. New row → `revision 1`; each later change → `+1`, `updated_via = via`, auto-stamp `applied_at` when `applied` flips true and no date was given. |
| `services.applications.ApplicationService` | `get(job_id) -> ApplicationView` (404 until first patch) · `patch(job_id, ApplicationPatch) -> ApplicationView` (404 on unknown job). Own `session_factory`. |
| `schemas.applications.ApplicationPatch` | `extra="forbid"`, every field optional, `Literal` enum aliases, rejects an empty body. Carries only user-owned fields. |
| `exports.layout` | `COLUMNS` (9 visible + `job_id`/`revision` hidden), `EDITABLE_FIELDS`. |
| `exports.excel.write_workbook` / `read_workbook` | `list[ExportRow] -> bytes` / `bytes -> list[ParsedRow]`. Pure; `read_workbook` coerces cells and puts a bad cell on `ParsedRow.parse_error` rather than raising. A structurally broken file raises `WorkbookError` (→ 422). |
| `services.exports.ExportService` | `export_xlsx() -> (filename, bytes)` snapshot · `import_xlsx(filename, data, *, commit=False) -> ImportReport`. Reconcile keyed on `job_id`, `revision` guard, dry-run default, atomic + audited commit. |

## 5. Schema & ERD

The schema, ERD, and load-bearing constraints are in **[`docs/data-model.md`](data-model.md)**
(day 3). ORM models live in `app/models/`; `app/db/base.py` holds the `Base` + constraint
naming convention; `app/db/session.py` owns the engine and `session_scope()`. Migrations are
in `migrations/`, one initial revision so far (`0001`). Rationale for the key decisions:
ADR-0002 (idempotency anchor), ADR-0003 (canonical vs. source-posting split), ADR-0011
(write-ownership: FK `RESTRICT`, no triggers).

## 6. Ingestion, relevance & idempotency

Pipeline: `fetch → parse → identify → relevance filter → idempotent persist → run log`.
`IngestionRunner.run()` (day 6) drives it; per-posting steps are `ingestion/pipeline.prepare()`;
persistence crosses the port seam into `services/ingestion.py`. See §4 for the interfaces.

- **Idempotency anchor (ADR-0002):** `source_postings.dedup_key = coalesce(source_job_id, canonical_url)`, `NOT NULL`, `UNIQUE (source_id, dedup_key)`, plus a partial unique index on `(source_id, source_job_id) WHERE source_job_id IS NOT NULL`. `INSERT … ON CONFLICT … DO UPDATE` classifies inserted / updated / unchanged via `xmax = 0` + `content_hash` comparison.
- **Relevance filter (ADR-0009):** a core pipeline stage, not an AI-layer add-on. Deterministic `evaluate(posting, ruleset)` combining title function-match + title-only seniority tokens + parsed minimum experience — never a body substring scan. Rejects go to `filtered_postings` (its own `(source_id, dedup_key)` uniqueness, no FK into `jobs`) and never reach the `jobs` table. Bias: keep on ambiguity, marked `weak`.
- **Write-ownership invariant (ADR-0011):** ingestion may insert/update `companies`, `jobs`, `source_postings`, `filtered_postings`, `ingestion_*` — and must never create, update, or delete an `applications` row. `app/ingestion/` cannot even import `app/db` (import-linter); it writes through ports whose only ORM implementations (`services/ingestion.py`) touch canonical tables. Also enforced by FK `ON DELETE RESTRICT`, zero database triggers, and an integration test that double-runs ingestion over a job with an `applications` row and asserts the row is unchanged.
- **Reliability:** per-source `pg_try_advisory_xact_lock` (a run that doesn't get it finishes `skipped`, no run row), `tenacity` retry around `fetch()` on `SourceUnavailable` (the `HttpClient` also retries individual requests and honours a small `Retry-After`), per-source token-bucket rate limiting inside the adapter, per-posting failure isolation via a `SAVEPOINT` per posting → `ingestion_errors` row, run finishes `partial`.

## 7. API design

REST under `/api/v1`. Auth (ADR-0008): a single static bearer token, **server-side only** —
never shipped to any client. Errors are RFC 7807 `application/problem+json` (`app/api/errors.py`),
including reshaped validation errors and a leak-free catch-all 500.

| Method + path | Auth | Handler | Notes |
|---|---|---|---|
| `GET /health`, `GET /health/ready` | public | `services.health` | 503 if the DB is unreachable |
| `GET /jobs` | public | `JobService.search` | query params → `JobFilters` (`q`, `company`, `source`, `remote`, `status`, `limit` 1–200, `offset`); redacted (`JobSummary` has no private fields) |
| `GET /jobs/{id}` | public | `JobService.get` | 404 problem if missing; redacted |
| `POST /ingestion/runs` | **token** | `IngestionService.run_source` / `run_all` | body `{source, targets}` **or** `{plan}` (exactly one); runs synchronously, returns `IngestionReport`; unknown slug → 400, unseeded slug → 409 |
| `GET /ingestion/runs` | **token** | `IngestionService.recent_runs` | `limit` 1–100, newest first |
| `GET /ingestion/runs/{id}` | **token** | `IngestionService.get_run` | 404 problem if missing |
| `GET /jobs/{id}/application` | **token** | `ApplicationService.get` | my private record; 404 problem until the first PATCH |
| `PATCH /jobs/{id}/application` | **token** | `ApplicationService.patch` | body `ApplicationPatch` (user-owned fields only, `extra="forbid"`); creates on first call, bumps `revision` after; empty body → 422 |
| `GET /exports/xlsx` | **token** | `ExportService.export_xlsx` | streams the snapshot as an `.xlsx` attachment |
| `POST /exports/import` | **token** | `ExportService.import_xlsx` | `.xlsx` as the **raw body**; `?commit=false` (default) = dry run → `ImportReport`; `?commit=true` applies + audits |
| `GET /metrics` | **token** | `observability.metrics.render_prometheus` | in-process counters + timing, Prometheus text |

Later (post-MVP): `GET /sources`.
The bearer check is a router-level dependency on the protected groups, so it can't be
forgotten on a new route. Redaction is structural — private data is a separate protected
endpoint, not an authenticated view of a public one.

## 8. Excel export & import

PostgreSQL is the single source of truth (ADR-0005 revised). Excel is a *view + batch-edit
form* for the fields I own, applied through a reviewed import (ADR-0010) — never a live sync.

**Layout** (`app/exports/layout.py`) — one row per job:

| Read-only context | Editable (imported back) | Hidden |
|---|---|---|
| `Title` · `Company` · `URL` | `Applied` · `Applied At` · `Networking` · `Outcome` · `Application URL` · `Notes` | `job_id` (reconcile key) · `revision` (stale-write guard) |

**Export** — `ExportService.export_xlsx()` snapshots every job + its application state (defaults
for jobs with no record yet, `revision = 0`). `app/exports/excel.py` does `.xlsx ↔ rows` with
openpyxl and nothing else.

**Import** — `ExportService.import_xlsx(filename, data, *, commit=False)`:

- keyed on hidden `job_id`; the write goes through `ApplicationPatch` (`extra="forbid"`) so only
  editable fields can land and a canonical `jobs` field is unwritable (ADR-0011).
- **dry-run unless `commit=True`** — returns an `ImportReport`: per row `created`/`updated`/
  `unchanged`/`conflict`/`error`, the field-level `changes`, and `counts`.
- **revision guard** — sheet `revision` ≠ live `applications.revision` → `conflict`, row skipped
  even on commit, both numbers reported.
- unknown `job_id` / bad enum / unparseable cell → an `error` *row*; a non-`.xlsx` or a sheet
  missing `job_id` → 422 for the whole request.
- a commit is atomic, bumps `revision`, stamps `updated_via = "excel_import"` (same
  `write_application` helper as the API `PATCH`), and writes one `application_import_runs` audit
  row (`filename`, `counts`, full per-row report as JSONB).

## 9. Deployment

**Neon (Postgres) + one Render Docker `web` service + a GitHub Actions cron** (ADR-0006).
12-factor: all config from env, the container stateless, DB reached only via `DATABASE_URL`
(scheme `postgresql+psycopg://`). `render.yaml` is a Render Blueprint; `autoDeploy` on push to
`main` after CI. Health check is `/api/v1/health/ready` (503 → deploy held).

- **Migrations run out of band, never on container start** — `render.yaml`'s `preDeployCommand`
  (`alembic upgrade head && python -m scripts.seed_sources`) on paid instances; by hand on free.
  The `Dockerfile` `CMD` is only `uvicorn`.
- **Scheduled ingestion is `.github/workflows/ingest.yml`** — every 6h it runs
  `python -m scripts.run_ingestion` against Neon *directly* (no dependency on the web service
  being awake), reading the board/account list from `config/sources.yml`. Exits non-zero on any
  `failed` source. `nightly-live.yml` runs the `@live` adapter tests daily.
- **Scripts** (`scripts/`, mypy-strict + ruff like `app/`): `seed_sources` (idempotent),
  `run_ingestion` (cron entrypoint + `make ingest`).

Operational detail — first-time setup, routine ops, incident playbook — is in
[`docs/runbook.md`](runbook.md).

## 10. CI/CD & testing

`.github/workflows/ci.yml` (push to `main` + every PR): **`lint`** (ruff + ruff-format +
mypy `--strict` over `app/` **and `scripts/`** + import-linter + advisory pip-audit) and
**`test`** (a `postgres:16` service, `alembic upgrade head` / `downgrade base` round-trip,
`alembic check` so models can't drift from the migration, `pytest --cov`, and a ≥ 95% gate on
`deduplication/` + `discovery/` + `ingestion/`). Integration tests under `tests/integration/`
skip themselves when `DATABASE_URL` isn't a reachable `postgresql://` URL. `@pytest.mark.live`
tests are excluded by `-m 'not live'` and run in **`nightly-live.yml`** instead. Image build +
deploy is Render's; scheduled discovery is **`ingest.yml`** (§9). See §10 of the design blueprint
(linked from ADR-0001) for the full testing-boundaries table.

**`pip-audit` is visible, not blocking** (`continue-on-error: true` in the `lint` job). It scans
against a CVE database that changes independently of this repo's commits — a hard-fail gate on it
means CI can turn red on a day with no code changes at all (this happened for real on Day 1: a
fresh dependency install already carried unrelated transitive-dependency advisories). It still
runs on every push so findings are visible in the Actions log; remediation is a deliberate,
separate decision (bump a pin, or accept and move on), not a merge-blocker tied to someone else's
database.

## 11. Not used (deliberately)

Celery/Redis, Kafka/RabbitMQ, Kubernetes, Airflow/Dagster/Prefect, Ray/Spark/Dask,
Elasticsearch, a dedicated vector DB, GraphQL, MongoDB, Playwright (for now), managed
auth platforms, Terraform, database triggers, live Excel sync, and per-posting LLM
classification. Each has a one-line reason and a "reconsider when" trigger in the design
blueprint referenced from ADR-0001 — repeating the full table here would drift out of sync
with it, so it isn't duplicated in this file.
