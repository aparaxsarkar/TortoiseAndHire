"""Shared FastAPI dependencies: auth, service providers, query parsing.

Routes only ever depend on things from here or from `app/services/` - the
`import-linter` contract keeps `app/api/` from reaching into `db/` / `sources/` /
`ingestion/` directly.
"""

from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import Depends, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.api.errors import ProblemException
from app.core.config import Settings, get_settings
from app.schemas.jobs import JobFilters
from app.services.ingestion import IngestionService
from app.services.jobs import JobService

_bearer = HTTPBearer(auto_error=False, description="Static server-side token (ADR-0008)")


def require_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    presented = credentials.credentials if credentials is not None else ""
    if not secrets.compare_digest(presented, settings.api_token):
        raise ProblemException(
            status=401,
            title="Unauthorized",
            detail="A valid bearer token is required for this endpoint.",
        )


def get_job_service() -> JobService:
    return JobService()


def get_ingestion_service() -> IngestionService:
    return IngestionService()


def job_filters(
    q: Annotated[str | None, Query(description="case-insensitive title substring")] = None,
    company: Annotated[str | None, Query(description="case-insensitive company substring")] = None,
    source: Annotated[str | None, Query(description="only jobs seen from this source slug")] = None,
    remote: Annotated[bool | None, Query()] = None,
    status: Annotated[str | None, Query(description="open | closed | unknown")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> JobFilters:
    return JobFilters(
        q=q,
        company=company,
        source=source,
        remote=remote,
        status=status,
        limit=limit,
        offset=offset,
    )
