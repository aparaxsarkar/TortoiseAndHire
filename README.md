# TortoiseAndHire

*The hare naps and still loses. Here, you get to nap and still win —
TortoiseAndHire keeps discovering, filtering, and tracking jobs while you're
away from the keyboard.*

A personal job-search automation platform: discovers postings from ATS feeds
(Greenhouse and Lever today; Ashby/Workday are the same `JobSource` contract),
stores them in PostgreSQL with source-level idempotency, filters them to
relevant roles before they're ever persisted, and tracks applications — with a
strict, enforced boundary between job discovery (system-owned) and application
tracking (user-owned).

Status: **MVP complete** (10-day build). Discovery pipeline, deterministic
relevance filter, idempotent persistence, a public read API + a token-gated
write/ops API (RFC 7807 errors), the Excel round-trip, and deployment
(Neon + Render + a GitHub Actions ingestion cron) are all in place and tested.

## Design

The full architecture — layered module boundaries, PostgreSQL schema and ERD,
ingestion/idempotency design, API design, the Excel round-trip, deployment, and
the CI/CD + testing plan — is in [`docs/architecture.md`](docs/architecture.md),
with each locked decision recorded in [`docs/adr/`](docs/adr/). Operations live
in [`docs/runbook.md`](docs/runbook.md).

## Development

```bash
python -m venv .venv && source .venv/bin/activate
make install      # pip install -e ".[dev]"
make up           # postgres via docker compose
make lint         # ruff + format check
make typecheck    # mypy --strict on app/
make imports      # import-linter layer contracts
make test         # pytest
```

```bash
make migrate      # alembic upgrade head
make seed         # insert the `sources` rows (idempotent)
make run          # uvicorn app.main:app --reload
make ingest       # run discovery for config/sources.yml  (make ingest s=greenhouse for one)
```

Copy `.env.example` to `.env` before running anything that touches the
database or the API.

## Deploy

Neon (Postgres) + a Render Docker service + a GitHub Actions cron for scheduled
ingestion. `render.yaml` is a Render Blueprint. Full setup and the incident
playbook are in [`docs/runbook.md`](docs/runbook.md); the rationale is
[ADR-0006](docs/adr/0006-deployment.md).

## Repository layout

```
app/
├── api/           HTTP layer — routing, request/response schemas, auth, error mapping
├── core/          Config, logging, retry, rate-limit, observability — cross-cutting, imports nothing from app/
├── db/            Session + repositories — persistence operations only, no business rules
├── models/        SQLAlchemy ORM — persistence shape only
├── schemas/       Pydantic contracts — the canonical posting model + API DTOs
├── services/      Business logic; wires adapters + repositories + the ingestion runner
├── sources/       Fetch/parse/normalize per ATS — no DB access, no business logic
├── ingestion/     Run orchestration: retries, rate-limiting, the relevance gate, partial failure
├── deduplication/ Deterministic source-identity key + URL canonicalization — pure
├── discovery/     Deterministic relevance filter — pure, config-driven
└── exports/       Excel write + read (round-trip) — no DB
```

Module responsibilities and the enforced dependency rules are in
`docs/architecture.md` §3 and codified as `import-linter` contracts in
`pyproject.toml`.
