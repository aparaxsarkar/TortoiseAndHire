# Day 1 recap — the repository harness

A plain-language record of what Day 1 built and why, kept for reference as the
project grows. Day 1 wrote **zero lines of application code**. It built the
construction site: tooling, structure, and automatic checks, so that every
piece of real code from Day 2 onward lands somewhere with rules already
enforcing themselves.

## What we did, in order

### 1. A "build vs. reuse" audit
Two other job-search projects were in the workspace (`JobSpy-main`,
`ai-job-search-master`). Before writing code, we read their actual source to
decide whether to depend on them. **Verdict: reference only** — one had no
tests and didn't cover our sources anyway; the other wasn't a real backend.
The reasoning is written down permanently in
[`docs/adr/0012-...`](adr/0012-third-party-reuse-jobspy-and-ai-job-search.md)
and the notes in [`docs/reference/`](reference/).

### 2. The skeleton
Created ~14 empty Python packages (a folder becomes an importable *package* the
moment it holds an `__init__.py`, even an empty one). Each folder is a
placeholder for one specific responsibility, decided up front from the
architecture design. No real logic yet — just labeled boxes.

### 3. `pyproject.toml` — the project's control panel
One file that lists the external libraries the project needs **and** configures
every dev tool. Modern Python consolidates what used to be 3–4 separate files
here.

### 4. Three kinds of automated check
The core lesson: *rules you only write in a doc get broken; rules a machine
checks don't.*

| Tool | What it does |
|---|---|
| **`ruff`** (lint) | Reads code without running it; flags style issues and common mistakes. An instant, tireless reviewer for the small stuff. |
| **`mypy`** (type check) | Python lets you annotate types (`def f(x: int) -> str`); `mypy` verifies every piece of code honors those promises. Catches a large class of bugs before the program runs. |
| **`import-linter`** (architecture) | Reads every `import` statement and **fails the build** if a forbidden dependency appears — e.g. "the API layer may not touch the database directly." Turns an architecture diagram into an enforced, testable rule. 6 contracts are active. |
| **`pytest`** (tests) | Runs your code and checks the output is what you expected, so a future change can't silently break something that worked. |

### 5. Docker & `docker-compose`
A **container** packages the app plus everything it needs to run, so it behaves
identically everywhere — fixing "works on my machine." `docker-compose.yml`
describes multiple containers that run together (our future API + a Postgres
database) and starts them with one command.

### 6. CI/CD — GitHub Actions
**CI (Continuous Integration):** every push spins up a fresh machine on GitHub
and runs all the checks above, so a mistake surfaces in ~a minute, not weeks
later. **CD (Continuous Deployment)** — the automatic "ship it to a live
server" half — is not built yet.

### 7. The CI failure, and what it taught us
The first push turned CI red. Everything we wrote passed; the one failing step
was `pip-audit`, a scanner that checks our dependencies against a public
vulnerability database — and it found pre-existing issues in *third-party*
libraries, unrelated to our code. Lesson: distinguish **"the code is wrong"**
failures from **"the world changed under us"** failures. We changed the config
so `pip-audit` still runs and reports, but no longer blocks the build (that
database updates independently of our commits, so a hard-fail gate can turn CI
red on a day we changed nothing). Recorded in `docs/architecture.md` §10.

### 8. Decisions written down: ADRs
An **Architecture Decision Record** is a short, numbered file: *we decided X,
here's why, here's what it costs.* Six months later, or on a new contributor's
first day, the reasoning behind a non-obvious constraint is one file away
instead of a guess. `docs/adr/` holds them.

### 9. Git commits as a story
Git keeps a full history as snapshots ("commits"). Each commit got a
multi-line message explaining *why*, so `git log` reads as the project's
reasoning, not a pile of "fix stuff."

## Folder map

```
TortoiseAndHire/
├── app/                    ← ALL real application code (currently empty boxes)
│   ├── api/                HTTP endpoints. Talks to services/, never the database directly.
│   ├── core/              Shared plumbing: settings, logging, retry, rate limiting. Nothing job-specific.
│   ├── db/repositories/    The ONLY code allowed to write database queries — one file per stored thing.
│   ├── models/             Database table definitions (SQLAlchemy).
│   ├── schemas/            The shape of data moving through the system (Pydantic) — separate from DB tables.
│   ├── services/           Business logic — the rules; wires the other pieces together.
│   ├── sources/            One file per job board — fetch + parse only, no DB access.
│   ├── ingestion/          The conductor: runs a source, handles retries/limits, saves results.
│   ├── deduplication/      Pure logic: "have we seen this posting before?"
│   ├── discovery/          Pure logic: "is this posting relevant?" — runs before anything is saved.
│   └── exports/            Database rows ↔ Excel file, both directions.
├── tests/                  Mirrors app/ folder-for-folder.
├── docs/
│   ├── architecture.md     Living design reference — filled in as each piece is built.
│   ├── adr/                Numbered decision records.
│   └── reference/          Notes from the JobSpy / ai-job-search audit.
├── .github/workflows/ci.yml   What the CI robot checks on every push.
├── docker/Dockerfile + docker-compose.yml   How to package and run it consistently.
├── pyproject.toml          Dependencies + every tool's configuration.
├── Makefile                Shortcuts (`make test`).
├── .pre-commit-config.yaml Runs the same checks locally before you push.
├── .env.example            Template for local/secret configuration (real .env never committed).
└── .gitignore              Files git never tracks.
```

## Not built yet
No database connection, no API route, no job-fetching logic. Every folder above
is a labeled, empty box until Day 2.
