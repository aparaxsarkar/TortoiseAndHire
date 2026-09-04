# ADR-0012: Third-party reuse — `python-jobspy` and `ai-job-search`

## Status
Accepted — 2026-09-04

## Context
Two candidate repositories sat alongside JobScout in the workspace: `JobSpy-main`
(`python-jobspy`, a mature job-aggregator scraping library) and `ai-job-search-master` (an
AI-powered job-application framework). Both were audited by reading their actual source,
tests, dependencies, and CI — not their READMEs — against JobScout's locked design: ATS-native
sources (Greenhouse/Lever/Ashby/Workday), PostgreSQL as system of record, source-level
idempotency, the `jobs`/`source_postings` split, a deterministic pre-persistence relevance
filter (ADR-0009), and the ADR-0011 write-ownership invariant. Full findings, the cross-repo
comparison table, the 10-question architecture test, and the security/licensing/build-savings
assessment are preserved in the session that produced this ADR; this document records the
conclusions and what to do about them.

### JobSpy (`python-jobspy` v1.1.82, MIT © Cullen Watson)
- **Zero ATS-native coverage** (grep-confirmed) — it scrapes 8 *aggregators* (LinkedIn, Indeed,
  Glassdoor, Google Jobs, ZipRecruiter, Bayt, Naukri, BDJobs), none of which are JobScout's
  chosen sources. It cannot implement any of the four adapters this project needs.
- No tests at all; CI only publishes to PyPI. Single maintainer.
- `tls-client` (a bundled compiled Go shared library) is a portability/supply-chain risk;
  `pandas`/`numpy` sit on the import path for no benefit here.
- One source's exception aborts the whole multi-site call (`future.result()` unguarded);
  soft failures return an empty result indistinguishable from a real zero-result search.
- `Bayt`/`BDJobs` ids are `hash(url)` — salted by `PYTHONHASHSEED`, not stable across
  processes; unsafe as an idempotency key.
- `verify=False` on the Indeed call; a bare `requests.post` in Glassdoor bypasses the
  configured proxy; several hardcoded API keys / CSRF fallback tokens in `constant.py` files.
- It scrapes exactly the ToS-restricted aggregator category this project's design
  (`docs/architecture.md` §1, "favor permitted access methods") deliberately avoided.

### ai-job-search (MIT © Mads Lorentzen)
- Not a backend: no package, API, database, or schema. It is a Claude-Code fork-template —
  markdown skill/command specs executed by an agent, a flat CSV/JSON file store, Bun/TypeScript
  portal-search CLIs, and a LaTeX CV/cover-letter toolchain. There is nothing importable.
- Its own discovery/tracking separation (scrape state vs. application tracker, in separate
  files with a one-directional read) independently arrives at the same rule as ADR-0011 — it
  validates the design rather than threatening it, but its enforcement is prose + markdown
  tests, not schema constraints, and importing that *architecture* would be a regression here.
- Genuinely reusable *as reference*: a 5-dimension weighted job-fit rubric with eligibility/
  language pre-gates (`04-job-evaluation.md`), a pipeline-status/final-disposition two-enum
  vocabulary, a fail-closed RFC 9309 robots.txt gate (`tools/robots_check.py`, stdlib, own test
  suite), and a drafter → fresh-context-reviewer prompt architecture with a factual-grounding
  audit.

## Decision
Both repositories are **reference only**. Neither is added as a dependency, forked, or
vendored (with one narrow, deferred exception below). JobScout's four ATS adapters are
first-party code against public JSON feeds; nothing from either repo enters `app/sources/`,
`app/ingestion/`, `app/deduplication/`, `app/discovery/`, or any persistence path.

Two dated reference notes are checked in so the design intent is captured before the code
that depends on it is written:

- [`docs/reference/jobspy-adapter-contract.md`](../reference/jobspy-adapter-contract.md) —
  the `JobPost` field set, the per-source id scheme, and the `Scraper`/`ScraperInput`/
  `JobResponse` contract shape, informing `schemas/canonical.py` and `sources/base.py`.
- [`docs/reference/relevance-and-fit-rubric.md`](../reference/relevance-and-fit-rubric.md) —
  the weighted fit rubric, status vocabulary, and eligibility-gate pattern, informing
  `app/discovery/` now and the future `app/analysis/` JD-scoring service.

**Deferred, not decided:** a single wrapped `JobSpyAdapter` behind the `JobSource` protocol,
disabled by default, pinned to an exact `python-jobspy` version, may be added later *only if*
aggregator coverage (LinkedIn/Indeed) becomes a real requirement. It would get its own
`try/except` + timeout + run-status per call, derive `source_job_id` from native ids
(recomputing a stable hash for Bayt/BDJobs rather than trusting theirs), and bridge
`logging.getLogger("JobSpy:*")` into `structlog`. This is not scheduled in the MVP plan.

`tools/robots_check.py` may be adapted into `app/core/robots.py` (MIT notice retained) if and
when an adapter needs to fetch HTML rather than a JSON feed — none of the four MVP adapters do,
so this is also not scheduled.

## Consequences
- The MVP schedule (ADR-0001) is unchanged; this audit removed no critical-path work and adds
  none — reuse here is reference-level (patterns deliberately adopted), not dependency-level
  (work hidden behind someone else's library).
- `python-jobspy` does not appear in `pyproject.toml` for the MVP.
- If aggregator coverage is added later, it must land as one adapter behind `JobSource`,
  pinned, isolated, and independently tested — never via `scrape_jobs()`'s DataFrame path.
- The two reference docs are dated snapshots (of the audited repos as they stood on
  2026-09-04), not kept in sync with upstream; they are read once when the code they inform
  is written, not treated as a live dependency.
