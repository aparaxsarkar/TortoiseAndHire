# JobScout

A personal job-search automation platform: discovers postings from ATS feeds
(Greenhouse, Lever, Ashby, Workday), stores them in PostgreSQL with
source-level idempotency, filters them to relevant roles before they're ever
persisted, and tracks applications — with a strict, enforced boundary between
job discovery (system-owned) and application tracking (user-owned).

Status: **Day 1 — repository harness.** No application code yet.

## Design

The full architecture — layered module boundaries, PostgreSQL schema and ERD,
ingestion/idempotency design, API design, Excel export/import, deployment,
CI/CD and testing plan, and the 2-week MVP schedule — lives in the design
blueprint (see `docs/architecture.md`) and the decision records in
[`docs/adr/`](docs/adr/).

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

Copy `.env.example` to `.env` before running anything that touches the
database or the API.

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
