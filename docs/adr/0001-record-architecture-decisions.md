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
| 1 | Repo harness: `pyproject.toml`, `docker-compose.yml`, `Dockerfile`, `.env.example`, `Makefile`, pre-commit, empty `app/` packages, `ci.yml` (lint), import-linter contracts | **0001** (this file), **0012** |
| 2 | `core/`: config, logging, retry, rate-limit, observability; `main.py` + `/health` | 0002 (idempotency strategy, recorded early since it shapes `core/retry`) |
| 3 | DB layer: `db/base`, `session`, all `models/`, first Alembic migration | 0003 (canonical vs source-posting split), 0011 (write-ownership: FK `RESTRICT`, no triggers) |
| 4 | Repos + `deduplication/` + `discovery/` | 0009 (relevance filter before persistence) |
| 5 | `sources/` scaffolding + Greenhouse + Lever adapters | 0004 (adapter boundary, no DB) |
| 6 | `ingestion/`: runner, pipeline, results | 0004, 0009, 0011 (wired) |
| 7 | `services/`: `IngestionService`, `JobService.search` | — |
| 8 | API I: `routes/jobs`, `routes/ingestion`, auth, redaction | 0008 (server-side-only auth) |
| 9 | API II + Excel round-trip: `ApplicationService`, `exports/`, import | 0005 (revised: Excel round-trips user-owned fields), 0010 (revision guard / dry-run) |
| 10 | Deploy: Neon, Render, Actions cron, runbook | 0006 (deployment) |

(Cross-source dedup suggestions, if built, get ADR-0007 when that stretch work starts.)

## Consequences
- Every non-obvious constraint in the code (a `RESTRICT` instead of `CASCADE`, a filter that
  runs before persistence instead of after, a token that never reaches a client) has a
  written reason someone can find in under a minute.
- `docs/architecture.md` can be trusted as "what exists today" without re-deriving it from a
  git log, because it's updated in the same change that alters the shape it describes.
- The ADR set is a flat, growing list — no renumbering, no silent edits. A decision that
  changes gets a new ADR that supersedes the old one.
