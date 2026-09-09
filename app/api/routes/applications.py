"""Protected: my private application record for a job (ADR-0008, ADR-0011).

Separate router from the public `jobs` routes - same `/jobs` prefix, but every
route here carries the bearer-token dependency.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import get_application_service, require_token
from app.schemas.applications import ApplicationPatch, ApplicationView
from app.services.applications import ApplicationService

router = APIRouter(prefix="/jobs", tags=["applications"], dependencies=[Depends(require_token)])


@router.get("/{job_id}/application", response_model=ApplicationView)
def get_application(
    job_id: uuid.UUID,
    service: Annotated[ApplicationService, Depends(get_application_service)],
) -> ApplicationView:
    return service.get(job_id)  # ApplicationNotFound -> 404 problem


@router.patch("/{job_id}/application", response_model=ApplicationView)
def patch_application(
    job_id: uuid.UUID,
    patch: ApplicationPatch,
    service: Annotated[ApplicationService, Depends(get_application_service)],
) -> ApplicationView:
    return service.patch(job_id, patch)
