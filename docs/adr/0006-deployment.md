# ADR-0006: Deployment — Neon + Render + a GitHub Actions cron

## Status
Accepted — 2026-09-10

## Context
This is a single-user tool that needs to run somewhere cheap, keep discovering
jobs on a schedule, and be redeployable in one push. It does **not** need a
cluster, an orchestrator, a message broker, or infrastructure-as-code beyond a
single service declaration — those were on the blueprint's "Not used" list from
the start, and nothing since has changed that.

## Decision

**Managed Postgres (Neon) + one container on Render + a scheduled GitHub Actions
workflow for ingestion.** 12-factor throughout: all config from the environment,
the container stateless, the database reached only via `DATABASE_URL`.

### Database — Neon
- A Neon project; the API uses the **pooled** connection string. The scheme must
  be `postgresql+psycopg://` (SQLAlchemy selects the driver from the scheme; a
  bare `postgresql://` picks the uninstalled `psycopg2`).
- Neon is the system of record. No read replicas, no separate analytics store.

### API — Render (Docker)
- `render.yaml` (a Render Blueprint) declares one `web` service built from
  `docker/Dockerfile`. `autoDeploy: true` → a push to `main` that passes CI
  triggers a build + deploy. No `deploy.yml` — Render owns this.
- `healthCheckPath: /api/v1/health/ready` — Render polls it; a `503` (DB
  unreachable) holds the deploy rather than routing to a broken instance.
- **Migrations run out of band, never on container start.** Multiple instances
  starting at once would race, and a slow migration would fail the health check.
  `render.yaml` sets `preDeployCommand: "alembic upgrade head && python -m
  scripts.seed_sources"`. Render's free plan doesn't run `preDeployCommand`; on
  free, migrations are applied by hand once per schema change (Render Shell, or
  locally against the Neon URL) — acceptable because schema changes are rare and
  deliberate. The `Dockerfile` `CMD` is only `uvicorn`.
- The container runs as a non-root user; the image carries `app/`, `migrations/`,
  `config/`, `scripts/`.
- Free plan spins the service down after ~15 min idle → a cold start on the next
  request. Fine for a personal API; the cron is unaffected (see below).

### Scheduled ingestion — GitHub Actions, not the HTTP endpoint
`ingest.yml` runs every 6 hours: checkout → `pip install -e .` →
`python -m scripts.seed_sources` → `python -m scripts.run_ingestion`, with
`DATABASE_URL` from a repo secret.

It talks to the **database directly**, not `POST /ingestion/runs`. Reasons: no
dependency on the (possibly spun-down) web service; the cron is exactly as
reliable as GitHub Actions + Neon; and the per-source advisory lock
(`pg_try_advisory_xact_lock`) already makes a run that overlaps a manual API
trigger safe. `scripts/run_ingestion.py` reads `config/sources.yml` (checked in,
public board tokens) and exits non-zero if any source's run ends `failed`, so a
broken adapter shows as a red workflow run.

`nightly-live.yml` runs the `@live` adapter smoke tests against real Greenhouse
and Lever once a day — a board changing its response shape turns it red within a
day and blocks nothing.

### Frontend
Out of MVP scope. If built, Cloudflare Pages / static host, shipping **no**
credential (ADR-0008) — functionally a read-only view of `GET /jobs`.

## Consequences
- Redeploy = `git push`. Rollback = redeploy the previous commit (Render keeps
  prior deploys) or `git revert`; a bad migration is `alembic downgrade` run the
  same out-of-band way it went up.
- Two secrets to manage: `DATABASE_URL` (Render env + GitHub Actions secret) and
  `TORTOISEANDHIRE_API_TOKEN` (Render env). Rotating the token is an env change +
  redeploy.
- Total run cost at rest: $0 (Neon free + Render free + Actions minutes).
- `docs/runbook.md` has the first-time setup and the incident playbook.
