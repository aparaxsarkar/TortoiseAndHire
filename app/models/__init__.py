"""ORM models. Importing this package registers every table on `Base.metadata`
(Alembic's env.py relies on that).
"""

from __future__ import annotations

from app.db.base import Base
from app.models.application import Application
from app.models.application_import_run import ApplicationImportRun
from app.models.company import Company
from app.models.filtered_posting import FilteredPosting
from app.models.ingestion_error import IngestionError
from app.models.ingestion_run import IngestionRun
from app.models.job import Job
from app.models.source import Source
from app.models.source_posting import SourcePosting

__all__ = [
    "Application",
    "ApplicationImportRun",
    "Base",
    "Company",
    "FilteredPosting",
    "IngestionError",
    "IngestionRun",
    "Job",
    "Source",
    "SourcePosting",
]
