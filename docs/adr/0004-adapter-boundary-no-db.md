# ADR-0004: Source-adapter boundary — fetch and parse only, no database

## Status
Accepted — 2026-09-07

## Context
Every job board speaks its own dialect: Greenhouse returns HTML-entity-encoded
`content` under `/boards/{token}/jobs?content=true`; Lever returns a flat JSON array
with `descriptionPlain` already split from `additionalPlain`; Ashby and Workday
(later) differ again. Something has to turn each of those into one shape the rest of
the pipeline can rely on.

The risk is that "something" grows. An adapter that can see the database starts
doing `get_or_create` on a company mid-fetch; one that knows about the relevance
ruleset starts skipping postings it judges irrelevant; one that imports the
ingestion runner starts owning retry policy. Each of those is a real temptation and
each one couples a fragile, external-API-shaped module to the core, so a board
changing a field name can now break persistence or filtering.

## Decision
An adapter's entire job is **feed bytes → `CanonicalPosting`**. It does two things
and imports almost nothing.

- **`JobSource` is a `Protocol`** (`app/sources/base.py`): a `slug` ClassVar, an
  async `fetch(query: SourceQuery) -> AsyncIterator[RawPosting]`, and a synchronous
  `parse(raw: RawPosting) -> CanonicalPosting`. `BaseSource` supplies the shared
  HTTP lifecycle (`aclose()`, async context manager); concrete adapters set `slug`,
  override `_make_http()` for a per-source rate limit / base URL, and implement the
  two methods. `runtime_checkable`, so a test can assert `isinstance(src, JobSource)`.
- **`fetch()` and `parse()` are split on purpose.** `fetch()` does the network I/O
  and yields one `RawPosting` (provider JSON, untouched, plus a couple of `_`-prefixed
  context keys) per posting. `parse()` is pure and takes exactly one `RawPosting`.
  A malformed posting raises `SourcePayloadError` from `parse()` and the ingestion
  runner (Day 6) records that one and continues — a bad row can't sink the batch.
- **Allowed imports:** `app/schemas/canonical`, and `app/core/` (the HTTP wrapper,
  retry, rate-limit, logging, the error base). Nothing else.
- **Forbidden imports:** `app/db/`, `app/models/`, `app/services/`, `app/ingestion/`,
  `app/discovery/`, `app/api/`, and SQLAlchemy. Enforced by an `import-linter`
  contract ("`sources/` has no DB access and no business logic"), checked in CI.
- **No decisions about the posting.** An adapter never judges relevance, never
  dedups, never resolves a company, never decides whether to retry a run. It hands
  every posting it can parse to the caller. `remote` / `department` / `posted_at`
  are best-effort *extractions*, not *judgements*.
- **HTTP is shared, not per-adapter** (`app/sources/http.py`): one `httpx.AsyncClient`
  per adapter instance with an honest `User-Agent` that names the tool (never a
  browser impersonation), a per-source `TokenBucket`, `tenacity` retry on
  `SourceUnavailable`, and HTTP status mapped to the `SourceError` taxonomy
  (`SourceUnavailable` 5xx/timeout, `SourceRateLimited` 429, `SourceAuthError`
  401/403, `SourcePayloadError` 4xx / unparseable). A `429` with a small
  `Retry-After` is honoured once here; a larger one is raised for the runner to
  decide on.
- **`registry.get_source(slug)`** is the only lookup path; `available()` lists the
  registered slugs. The ingestion service resolves a source by slug through here and
  never imports a concrete adapter class.

The `CanonicalPosting` field set and the `fetch`/`parse` split shape are informed by
`python-jobspy`'s `Scraper` / `JobResponse` contract (see ADR-0012 and
`docs/reference/jobspy-adapter-contract.md`) — the shape was adopted, the dependency
was not.

## Consequences
- A board changing its JSON breaks one adapter and its unit tests, nothing
  downstream. Adapters are the most fragile code in the repo and they are now also
  the most isolated.
- Adapter tests need no database and no network: `respx` mocks the HTTP layer,
  JSON fixtures (`tests/fixtures/{greenhouse,lever}/`) stand in for real feeds.
  `HttpClient` takes `retry_attempts` / `retry_backoff` so tests exercise the retry
  path without real sleeps.
- Live smoke tests (`tests/unit/sources/test_live.py`, `@pytest.mark.live`) hit real
  public boards. They are excluded from CI (`-m 'not live'` in `pyproject.toml`) and
  are allowed to be flaky — they only tell us a board's shape hasn't drifted.
- Adding Ashby / Workday later is a new file implementing the same `Protocol` plus a
  registry line — no change anywhere else.
- The runner (Day 6) owns everything the adapter refuses to: retry accounting across
  a run, the advisory lock, the relevance gate, `ingestion_runs` / `ingestion_errors`,
  and per-posting failure isolation.

## Addendum — 2026-09-11: Ashby + Workday adapters

Added as first-party adapters. No change to the boundary — both are `JobSource`
implementations that only fetch and parse. What the two of them needed that
Greenhouse/Lever didn't, all contained in their own files:

- **`HttpClient` gained `post_json`** — same retry / rate-limit / status→error path
  as `get_json`, just POST + JSON body. Workday's list endpoint
  (`wday/cxs/{tenant}/{site}/jobs`) is POST-only. `Accept-Language: en-US` was
  added to the shared default headers (Workday localises its list strings).
- **Ashby** (`api.ashbyhq.com/posting-api/job-board/{board}`) is as clean as Lever:
  one GET, a UUID `id`, both HTML and plain descriptions, a structured address.
  No company name in the response, so it's derived from the board token.
- **Workday has no universal schema** — every tenant differs by shard
  (`wd1`/`wd3`/`wd5`) and site (`External`, `jobs`, `NVIDIAExternalCareerSite`, …),
  so a target is `tenant:shard:site`, configured in `config/sources.yml`. The list
  call gives only title / path / localised strings; the description and a real
  date come from a per-posting detail GET. A detail GET that fails is caught inside
  `fetch()` and the posting is yielded list-only (identity then falls back to the
  req id parsed from the path). A tenant is capped at 300 postings/run.
- `CanonicalPosting` was **not** changed. Source-specific extras (`applyUrl`,
  `workday_req_id`, `additional_locations`, …) live in `source_metadata`.
- The `sources/ have no DB access and no business logic` contract still holds; the
  new `@live` smoke tests (Ashby `posthog`, Workday `nvidia`) stay out of CI.
