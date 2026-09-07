# ADR-0009: Deterministic relevance filter, before persistence

## Status
Accepted — 2026-09-07

## Context
Ingesting every posting a board exposes fills the database with HR, sales, senior,
and 5-plus-years roles — thousands of rows to make the handful I care about harder
to find. Filtering has to happen, and the question is *where* and *how*: after
persistence (query-time), or before; with an LLM, or with rules.

## Decision
A **deterministic, rule-based** filter runs as a core pipeline stage, **between
identity derivation and persistence**. No LLM call on the ingest path.

- The ruleset lives in `config/discovery.yml` — checked in, version-stamped, loaded
  once per run (`app/discovery/ruleset.py`).
- `evaluate(posting, ruleset)` (`app/discovery/rules.py`) combines three signals:
  1. **title function match** — the title must contain one of `target_functions`;
  2. **seniority tokens in the *title only*** — `exclude_title_tokens` matched at a
     word boundary (so "you'll work with senior engineers" in the body does not
     reject);
  3. **parsed minimum experience** — `app/discovery/experience.py` pulls a required
     years-of-experience number out of the description; reject if it exceeds
     `max_experience_years`.
  Plus optional internship and location gates. The location gate is a dumb
  string/region match and never infers work authorisation, visa, or sponsorship.
- **Bias: keep on ambiguity.** A title that matches a function and trips no reject
  rule is kept. If nothing corroborates "early career" (no target-level word, no
  parsed-and-acceptable experience number, not remote) the verdict is `matched=True,
  strength="weak"` — kept, but a ranker should rank it lower. A false positive is
  one manual dismiss; a false negative is invisible.
- **Rejected postings go to `filtered_postings`**, not `jobs` — same
  `(source_id, dedup_key)` idempotency as `source_postings`, but no FK into `jobs`.
  `raw_payload` is retained so a newer ruleset can be replayed without re-fetching.
- Run stats gain `matched` and `filtered_out` counts, so a run reports e.g.
  "fetched 847 · matched 96 · new 17".

The LLM's role is *later* (Week 3–4): a re-score with an explanation
("titled Staff, but the body targets early career") that **refines, never replaces**
this gate, runs nightly over already-persisted jobs, and never per-posting on ingest.
See the reference note `docs/reference/relevance-and-fit-rubric.md`.

## Consequences
- The database stays useful — it holds roles I might apply to, plus an auditable
  ledger of what was screened out and why.
- The filter is pure and has a ≥ 95% coverage gate in CI (`app/discovery/*`), so the
  worked examples (and the "seniority word in the body doesn't reject" edge) are
  pinned.
- Tuning is a config edit + a version bump; `scripts/reevaluate_filtered.py` (later)
  replays a new ruleset over `filtered_postings` and promotes fresh matches.
- Experience parsing is heuristic and biased toward `None` (keep): a bare "5 years"
  with no qualifier and no "experience" nearby is treated as ambiguous, not a
  requirement.
