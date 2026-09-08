# ADR-0008: Server-side-only bearer token; public reads are redacted

## Status
Accepted — 2026-09-08

## Context
TortoiseAndHire is a single-user tool with a public demo. Two things must both be
true: the demo can show the job list to anyone, and my private application /
networking / notes data is never exposed, nor is any credential that could be
used to write.

A login system (users, sessions, password hashing) is overkill for one user. A
single static token is enough — *if* it never reaches a browser. The failure mode
to design against is a token baked into a frontend bundle or an HTML page, where
"view source" hands an attacker write access.

## Decision

**One static bearer token, `Settings.api_token` (env `TORTOISEANDHIRE_API_TOKEN`),
checked server-side only.** It is never sent to a client, never embedded in a
page, never in the deployed React bundle.

Route split:

| Public — no auth | Protected — `Authorization: Bearer <token>` |
|---|---|
| `GET /api/v1/jobs`, `GET /api/v1/jobs/{id}` | `POST /api/v1/ingestion/runs` |
| `GET /api/v1/health`, `/health/ready` | `GET /api/v1/ingestion/runs`, `/runs/{id}` |
| (`GET /sources` — later) | (all writes, `/jobs/{id}/application`, `/exports/*`, `/metrics` — later) |

- **The check** (`app/api/deps.py::require_token`): `HTTPBearer(auto_error=False)`
  extracts the credential, `secrets.compare_digest` compares it (constant-time),
  a mismatch or absence raises `ProblemException(401)`. Protected routers carry it
  as a router-level `dependencies=[Depends(require_token)]`, so it runs before the
  body is parsed and can't be forgotten on a new route in that group.
- **Redaction is structural, not a filter.** Private data lives on the
  `applications` table. The public job endpoints return `JobSummary`, which has no
  application/networking/notes fields and no `applied`/`outcome` query filter —
  there is nothing to redact because the shape never carries it. Private data is a
  separate protected endpoint (`GET /jobs/{id}/application`, day 9), not an
  authenticated variant of the public one. An API test asserts a `GET /jobs/{id}`
  body contains none of those keys, locking the contract.
- **Errors are RFC 7807** `application/problem+json` everywhere
  (`app/api/errors.py`): `{type, title, status, detail}`. `ProblemException` for
  deliberate 4xx; handlers reshape FastAPI's validation errors, `HTTPException`,
  any `TortoiseError` (which carries its own `http_status`/`http_title` so `api/`
  needn't import specific subclasses), and a catch-all 500 that logs and leaks
  nothing.
- **The trigger is synchronous.** `POST /ingestion/runs` blocks until the run
  finishes and returns the report. No task queue (the blueprint's "Not used" list
  rules out Celery/Redis). Acceptable for a manual/scheduled single-user trigger;
  the endpoint is `async` so board fetches don't block the event loop.

## Consequences
- The deployed demo ships zero credentials and is functionally read-only. Writes
  run via `curl` / HTTPie / `scripts/` with the token in the environment.
- A future admin UI must keep the token server-side behind an HttpOnly session
  cookie — never in JavaScript. That constraint is inherited from this ADR.
- `import-linter` keeps `app/api/` from importing `app/db` / `app/sources` /
  `app/ingestion` directly, so a route can only reach data through a service —
  which is also what lets `require_token` and the redaction boundary stay in one
  place.
- If the token is the default `"change-me"`, the API still enforces it (you must
  send `Bearer change-me`). Rotating it is an env-var change + redeploy.
