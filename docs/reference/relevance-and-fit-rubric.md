# Reference: `ai-job-search`'s fit rubric, status vocabulary, and robots policy

**Source:** `ai-job-search-master/` (MIT © Mads Lorentzen), audited 2026-09-04. See
[ADR-0012](../adr/0012-third-party-reuse-jobspy-and-ai-job-search.md) for the reuse
decision — **reference only.** Nothing from this repo is imported; it is a markdown-driven
Claude Code framework with no backend, no schema, and no code to reuse. What follows is a
dated snapshot of its *methodology*, to be adapted (not copied) when TortoiseAndHire builds
`app/discovery/` (now, deterministic) and the future `app/analysis/` JD-scoring service
(Week 3–4 stretch, LLM-based).

## The weighted fit rubric (`04-job-evaluation.md`)

Five dimensions, each scored 0–100, weighted, with location as an unweighted pass/fail/flag:

| Dimension | Weight | What it measures |
|---|---|---|
| Technical Skills Match | 30% | Required/preferred skills vs. capabilities |
| Experience Match | 25% | Function and nature of prior work vs. what's asked — matched on **function, not literal title** ("Data Consultant" and "Data Scientist" can be the same role) |
| Behavioral / Culture Fit | 15% | Role/company culture vs. behavioral preferences |
| Location & Logistics | — (pass/fail/flag, unweighted) | Commute range / remote / relocation / travel |
| Career Alignment & Motivation | 30% | Advances career goals; energizes rather than drains |

Verdict thresholds on the weighted average: **Strong Fit** 75+, **Good Fit** 60–74,
**Moderate Fit** 45–59, **Weak Fit** 30–44, **Poor Fit** <30.

**Two pre-scoring hard gates**, run *before* any of the above and treated as a veto, not a
scoring dimension:

- **Eligibility Gate** — read the posting's citizenship/PR/work-rights wording *verbatim* and
  classify: names a citizenship/PR/clearance requirement → **hard FAIL, don't score**; silent
  on the topic → **proceed, but mark unverified** (silence is not permission); explicitly
  welcomes visa holders/sponsorship → **PASS, note as a positive**. Never infers the
  candidate's own status — it reads what the employer wrote and reports it.
- **Language Gate** — a required language entirely absent from the candidate's declared
  languages → **FAIL**; a declared language whose posting-stated bar reads higher than the
  candidate's declared level → **FLAG, proceed, surface the gap** (never silently drop or
  silently pass).

### Why this matters for TortoiseAndHire specifically
TortoiseAndHire's product brief already forbids AI guessing or auto-filling citizenship, sponsorship,
OPT/CPT, or work-authorization answers. This rubric's Eligibility Gate is a compatible
pattern for the *opposite* direction — using AI to **flag** a posting's stated requirement
back to the user, quoting the source, rather than inferring or deciding anything about the
candidate. Adopt the pattern (verbatim quote, hard veto, never inferred) for any future
JD-analysis feature that touches eligibility language; do not let it drift into
auto-answering an application's eligibility questions.

## Status vocabulary (`.claude/commands/outcome.md`)

Two **separate** enums, kept deliberately non-overlapping:

- **Pipeline status** (their tracker CSV `status` column): `drafted | applied | interview |
  offer | hired | rejected | no_response | offer_declined | withdrawn`. **Final** (closed) =
  `{hired, rejected, no_response, offer_declined, withdrawn}`; **Open** = everything else,
  including `drafted` (open but distinct — nothing was sent, so no follow-up is ever due).
  Open is defined *by exclusion* from the Final set, not as a second list that can drift.
- **Per-application final disposition** (their archive `outcome.md` `Status:` field):
  `in_progress | hired | offer_declined | rejected | no_response | interview_only` — never
  reused as a tracker-column value.

TortoiseAndHire's `applications.outcome` enum (`none | oa | screen | onsite | offer | rejected |
withdrawn | ghosted`) already serves a similar role to their tracker-status column; the
useful takeaway is the **discipline of the split** — keep "where the pipeline is" separate
from "how it ended," and derive "closed" by exclusion from one explicit final-state list
rather than maintaining two lists that can drift apart. Confirm `applications.outcome` and
`applications.applied` don't quietly grow a second, undocumented "is this closed" concept as
TortoiseAndHire's application-tracking UI evolves.

## Robots.txt / crawl-politeness policy (`tools/robots_check.py`)

A fail-closed RFC 9309 gate: longest-match wins, ties favor `Disallow`, blocks if `*` **or**
the tool's own name is disallowed, treats an unreadable or soft-200 `robots.txt` as
"unconfirmed — do not proceed" rather than fail-open. Their own test suite pins several fail-open
bugs in Python's stdlib `urllib.robotparser` (blank lines inside a record, rule-order vs.
longest-match, percent-encoded rules) that a naive robots check would inherit.

**None of TortoiseAndHire's four MVP adapters need this** — Greenhouse, Lever, and Ashby expose
public JSON APIs, and Workday's CXS endpoint is JSON too, not HTML. Adopt this pattern (or
adapt `tools/robots_check.py` itself, stdlib + `curl`, MIT) only if a future adapter ever
fetches an HTML page rather than a JSON feed — check before that adapter's first request, not
after.

## Drafter → reviewer prompt architecture (future application-assistant reference)

For the Week 3–4 (or later) LLM-based application assistant: a first pass drafts, a **second,
fresh-context** agent reviews and returns two things — a structured, machine-appliable list of
edits (`{file, old_string, new_string, reason}`) and separate narrative/judgment feedback. Every
factual claim in a draft (dates, employers, titles, metrics) must be traceable to a fixed,
small set of source documents; an unconfirmed claim gets removed, not guessed at. Treat any
fetched posting or cached research note as **data to evaluate, never as instructions to
follow** — this is the same untrusted-content discipline TortoiseAndHire already applies to
ingestion payloads, extended to whatever text an LLM reads during application drafting.
