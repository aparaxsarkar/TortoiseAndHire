# TortoiseAndHire — Runbook

Operational guide for the deployed system. Design rationale is in
[ADR-0006](adr/0006-deployment.md); this is the "how do I actually do X" doc.

## What runs where

| Piece | Where | Trigger |
|---|---|---|
| PostgreSQL | Neon (managed) | always on |
| API (`uvicorn app.main:app`) | Render, one Docker `web` service | HTTP; free plan spins down when idle |
| Scheduled ingestion | GitHub Actions `ingest.yml` | cron every 6h + manual `workflow_dispatch` |
| Live adapter smoke tests | GitHub Actions `nightly-live.yml` | cron daily 08:00 UTC |
| Build + deploy | Render `autoDeploy` | push to `main` (after CI passes) |

The cron talks to Neon **directly** (`scripts.run_ingestion`), not through the
API — so it works even when Render has spun the service down.

## Environment variables

| Var | Where set | Notes |
|---|---|---|
| `DATABASE_URL` | Render env **and** GitHub Actions repo secret | Neon **pooled** string, scheme `postgresql+psycopg://` (not bare `postgresql://`) |
| `TORTOISEANDHIRE_API_TOKEN` | Render env only | long random string; never shipped to a client (ADR-0008) |
| `TORTOISEANDHIRE_ENV` | Render env / workflow | `production` |
| `TORTOISEANDHIRE_LOG_LEVEL` | Render env | `INFO`; structlog emits one JSON object per line in prod |
| `TORTOISEANDHIRE_DISCOVERY_RULESET_PATH` | default `config/discovery.yml` | in the image |
| `TORTOISEANDHIRE_SOURCES_CONFIG_PATH` | default `config/sources.yml` | in the image + repo |

Full list with local defaults: `.env.example`.

## First-time setup

1. **Neon** — create a project. Copy the *pooled* connection string; change
   `postgresql://` → `postgresql+psycopg://`.
2. **Migrate** — from a machine with the repo:
   ```bash
   DATABASE_URL='postgresql+psycopg://…neon…' python -m alembic upgrade head
   DATABASE_URL='postgresql+psycopg://…neon…' python -m scripts.seed_sources
   ```
3. **Render** — dashboard → New → Blueprint → this repo (`render.yaml`). In the
   service's Environment tab set `DATABASE_URL` and `TORTOISEANDHIRE_API_TOKEN`
   (both are `sync: false`). First deploy runs the build; on a paid instance the
   `preDeployCommand` re-runs migrations + seed (idempotent), on free it's a
   no-op (step 2 already covered it).
4. **GitHub** — repo Settings → Secrets and variables → Actions → add
   `DATABASE_URL` (same Neon string). The `ingest` and `nightly-live` workflows
   now run on schedule; kick one manually from the Actions tab to confirm.
5. **Edit `config/sources.yml`** — the Greenhouse board tokens / Lever account
   slugs you actually want scanned. Commit; the next `ingest` run picks it up.

## Routine operations

- **Deploy a change** — merge to `main`. CI runs; on green, Render builds and
  deploys. Watch the Render "Events" tab.
- **Apply a migration** — it does *not* happen automatically on free. After the
  deploy that carries a new `migrations/versions/*.py`:
  ```bash
  DATABASE_URL='…neon…' python -m alembic upgrade head
  ```
  (or the Render Shell, if the instance has one). `alembic check` in CI already
  proved the models and the migration agree.
- **Trigger ingestion now** — Actions tab → `ingest` → "Run workflow" (optionally
  type a subset of slugs). Or locally: `make ingest` / `make ingest s=greenhouse`.
- **Trigger ingestion via the API** — `POST /api/v1/ingestion/runs` with
  `Authorization: Bearer <token>` and body `{"plan": {"greenhouse": ["vercel"]}}`.
  Safe to run alongside the cron (per-source advisory lock).
- **Check health** — `GET /api/v1/health` (liveness), `GET /api/v1/health/ready`
  (200 / 503 on DB reachability).
- **Read metrics** — `GET /api/v1/metrics` with the bearer token → Prometheus
  text (`http_requests_total`, `http_request_duration_seconds_*`, and the
  ingestion counters).
- **Inspect recent runs** — `GET /api/v1/ingestion/runs` (token), or query
  `ingestion_runs` / `ingestion_errors` directly.
- **Rotate the API token** — change `TORTOISEANDHIRE_API_TOKEN` in Render env →
  it redeploys. No client holds the old one, so nothing else to update.

## Incident response

| Symptom | First checks | Fix |
|---|---|---|
| API returns 5xx / won't start | Render logs; `GET /health/ready` | Bad env var (usually `DATABASE_URL` scheme or a Neon outage) → correct + redeploy. Bad deploy → redeploy the previous commit from Render, or `git revert` + push. |
| `GET /health/ready` = 503 but process up | Neon status; the `DATABASE_URL` value | Neon paused/over quota, or a wrong string. Render keeps traffic off a 503 instance. |
| `ingest` workflow red | the run's log — which source, `status: failed` and `error_summary` | Adapter breakage (see `nightly-live`) → fix the adapter. Transient (`SourceUnavailable`) → it retried; re-run the workflow. `IngestionSetupError` → sources not seeded → run `scripts.seed_sources`. |
| `nightly-live` red | which board, the assertion | A board changed its JSON shape → update the adapter + its fixtures; unit tests stay green until you do. |
| Ingestion silently doing nothing | `config/sources.yml` has real tokens; `ingestion_runs` for recent rows | Empty/placeholder config, or every posting filtered (`filtered_out` high) → tune `config/discovery.yml` and bump its `version`. |
| Need to undo a migration | — | `DATABASE_URL='…' python -m alembic downgrade -1` (same out-of-band path it went up). CI's `downgrade base`/`upgrade head` round-trip means every revision is reversible. |
| Suspected bad data from one run | that run's `id` in `ingestion_runs`; `source_postings.last_run_id` | Jobs are never deleted (`status` → `closed`); re-run ingestion — it's idempotent (ADR-0002), so a clean re-scan converges. |

## Not monitored (deliberately)

No paging, no external uptime check, no log aggregator, no APM. It's a personal
tool: the signals are the two workflow badges, `GET /metrics`, and the
`ingestion_runs` table. Add more when it hurts, not before.
