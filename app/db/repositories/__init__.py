"""Repositories: the only code that runs queries. CRUD + upsert, no business rules."""

from __future__ import annotations

from app.db.repositories.companies import CompanyRepository
from app.db.repositories.filtered_postings import FilteredPostingRepository
from app.db.repositories.jobs import JobRepository
from app.db.repositories.source_postings import SourcePostingRepository, UpsertOutcome
from app.db.repositories.sources import SourceRepository

__all__ = [
    "CompanyRepository",
    "FilteredPostingRepository",
    "JobRepository",
    "SourcePostingRepository",
    "SourceRepository",
    "UpsertOutcome",
]
