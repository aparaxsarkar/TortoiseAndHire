"""Repositories: the only code that runs queries. CRUD + upsert, no business rules."""

from __future__ import annotations

from app.db.repositories.applications import ApplicationRepository
from app.db.repositories.companies import CompanyRepository
from app.db.repositories.filtered_postings import FilteredPostingRepository
from app.db.repositories.ingestion_runs import IngestionRunRepository
from app.db.repositories.jobs import JobRepository
from app.db.repositories.source_postings import SourcePostingRepository, UpsertOutcome
from app.db.repositories.sources import SourceRepository

__all__ = [
    "ApplicationRepository",
    "CompanyRepository",
    "FilteredPostingRepository",
    "IngestionRunRepository",
    "JobRepository",
    "SourcePostingRepository",
    "SourceRepository",
    "UpsertOutcome",
]
