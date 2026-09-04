# Reference: `python-jobspy`'s adapter contract

**Source:** `JobSpy-main/` (`python-jobspy` v1.1.82, MIT © Cullen Watson & Zachary Hampton),
audited 2026-09-04. See [ADR-0012](../adr/0012-third-party-reuse-jobspy-and-ai-job-search.md)
for the reuse decision — **reference only, no dependency, no vendored code.** This is a dated
snapshot to inform `app/schemas/canonical.py` and `app/sources/base.py`; it is not kept in
sync with upstream.

## Why this is worth reading before writing `schemas/canonical.py`

JobSpy has shipped 8 scrapers long enough to have converged on a reasonable common shape for
"a job posting from somewhere." TortoiseAndHire's four ATS adapters are simpler (structured JSON,
not scraped HTML) but the *shape* of the contract — what a scraper promises to return, and how
identity is represented — is worth stealing even though the implementation is not.

## The contract shape

```python
class Scraper(ABC):
    def __init__(self, site, proxies=None, ca_cert=None, user_agent=None): ...

    @abstractmethod
    def scrape(self, scraper_input: ScraperInput) -> JobResponse: ...

class ScraperInput(BaseModel):
    site_type: list[Site]
    search_term: str | None
    location: str | None
    country: Country | None
    results_wanted: int = 15
    hours_old: int | None
    # ...

class JobResponse(BaseModel):
    jobs: list[JobPost] = []
```

Takeaway for TortoiseAndHire's `JobSource` protocol: a `SourceQuery` in (which boards/tenants to
pull), a list of normalized postings out, one method (`fetch`/`parse` split in TortoiseAndHire's
design rather than JobSpy's single `scrape`, so tests can feed canned `RawPosting`s straight
into `parse()` without a network layer). **Do not** copy `JobResponse` having no error/status
field — TortoiseAndHire's `IngestionRunResult` carries per-run stats and errors precisely because
JobSpy's silent-partial-result design (§ "What to avoid" below) is a real problem.

## `JobPost` field set (informs `CanonicalPosting`)

```python
class JobPost(BaseModel):
    id: str | None                  # source-prefixed, e.g. "li-3812..." — see identity below
    title: str
    company_name: str | None
    job_url: str                    # always populated; the de-facto dedup key JobSpy uses internally
    job_url_direct: str | None      # the employer/ATS apply URL, when discoverable
    location: Location | None       # city / state / country
    description: str | None
    company_url: str | None
    job_type: list[JobType] | None
    compensation: Compensation | None
    date_posted: date | None
    is_remote: bool | None
    # + several source-specific fields (job_level, company_industry, skills, ...)
```

Fields TortoiseAndHire's `CanonicalPosting` should have that `JobPost` doesn't need: `source_slug`,
`source_job_id` (kept distinct from a display `id`), `department`, `source_metadata: dict`
(an audit-trail catch-all for provider-specific extras) — JobPost instead bolts source-specific
fields directly onto the shared model (`job_level`, `skills`, `experience_range`, …), which is
fine for 8 sources with one shared DataFrame but would get noisy for TortoiseAndHire's schema-backed
model. Keep provider-specific extras in `source_metadata`, not as new columns.

## Per-source identity scheme (informs `source_job_id` derivation)

| Source | `id` construction | Stability |
|---|---|---|
| LinkedIn | `f"li-{job_id}"`, `job_id` parsed from the card's `href` | Stable — the site's own listing id |
| Indeed | `f'in-{job["key"]}'` | Stable — GraphQL response key |
| Glassdoor | `f"gd-{listingId}"` | Stable — GraphQL `listingId` |
| ZipRecruiter | `f'zr-{job["listing_key"]}'` | Stable |
| Naukri | `f"nk-{jobId}"` | Stable |
| Google | `f"go-{job_info[28]}"` | **Fragile** — a positional index into an undocumented JSON array |
| Bayt | `f"bayt-{abs(hash(job_url))}"` | **Not stable** — `hash()` of a `str` is salted by `PYTHONHASHSEED` per process |
| BDJobs | `hash(job_url)` fallback (prefers a `jobid=` URL param when present) | **Not stable** in the fallback case |

**Takeaway:** prefer the provider's own listing/posting id whenever the API exposes one
(Greenhouse `id`, Lever `id`, Ashby `id`, Workday `bulletFields`/`jobPostingId` — confirm per
adapter). If a source ever lacks one, TortoiseAndHire's own `deduplication/identity.py` falls back to
the **canonicalized URL**, never to a process-local `hash()` — see ADR-0002.

## What to avoid (concrete hazards, not just "it's a scraper")

- **No per-source failure isolation at the top level.** JobSpy's `scrape_jobs()` calls
  `future.result()` unguarded inside `as_completed`; an exception from one site's `.scrape()`
  discards every other site's already-finished results. TortoiseAndHire's `IngestionRunner` must
  isolate failures **per posting** (already designed — see `docs/architecture.md` §6) and
  never let one bad record abort a run.
- **Silent partial results.** A blocked/rate-limited source in JobSpy returns
  `JobResponse(jobs=[])` — indistinguishable from a genuine zero-result search. TortoiseAndHire's
  `ingestion_runs.stats` and `ingestion_errors` exist specifically so "fetched 0 because
  blocked" is never confused with "fetched 0, no jobs posted."
- **Global/mutable state under concurrency** — a module-level header dict mutated in place by
  every scraper instance (a real data race), a `StreamHandler` and `urllib3.disable_warnings`
  side effect at import time. TortoiseAndHire's adapters must be constructed per-call with no shared
  mutable module state, and logging goes through `structlog` from `core/logging.py`, never a
  handler attached inside `sources/`.
- **A heavy import for a thin job.** `pandas`/`numpy` load on `import jobspy` for a function
  that produces a list of dicts. TortoiseAndHire's adapters return `list[CanonicalPosting]` — no
  DataFrame anywhere in the pipeline.
