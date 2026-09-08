"""Protected ingestion control + history (ADR-0008).

Every route here requires the bearer token (router-level dependency). The trigger
runs synchronously - acceptable for a single-user tool with a manual/scheduled
trigger and no task queue (see the design blueprint's "Not used" list).
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_ingestion_service, require_token
from app.api.errors import ProblemException
from app.schemas.ingestion import (
    IngestionReport,
    IngestionRunSummary,
    RunRequest,
    SourceRunResult,
)
from app.services.ingestion import TRIGGER_MANUAL_API, IngestionService

router = APIRouter(prefix="/ingestion", tags=["ingestion"], dependencies=[Depends(require_token)])

_TRIGGER = TRIGGER_MANUAL_API


@router.post("/runs", response_model=IngestionReport)
async def trigger_run(
    body: RunRequest,
    service: Annotated[IngestionService, Depends(get_ingestion_service)],
) -> IngestionReport:
    if body.plan is not None:
        return await service.run_all(plan=body.plan, trigger=_TRIGGER)
    assert body.source is not None  # RunRequest validator guarantees one shape
    result: SourceRunResult = await service.run_source(
        body.source, targets=body.targets, trigger=_TRIGGER
    )
    return IngestionReport(results=[result])


@router.get("/runs", response_model=list[IngestionRunSummary])
def list_runs(
    service: Annotated[IngestionService, Depends(get_ingestion_service)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[IngestionRunSummary]:
    return service.recent_runs(limit=limit)


@router.get("/runs/{run_id}", response_model=IngestionRunSummary)
def get_run(
    run_id: uuid.UUID,
    service: Annotated[IngestionService, Depends(get_ingestion_service)],
) -> IngestionRunSummary:
    found = service.get_run(run_id)
    if found is None:
        raise ProblemException(status=404, title="Not Found", detail=f"No ingestion run {run_id}")
    return found
