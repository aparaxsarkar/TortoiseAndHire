"""Protected: the Excel round-trip (ADR-0005 revised, ADR-0010).

`GET /exports/xlsx` streams a snapshot. `POST /exports/import` takes the `.xlsx`
as the **raw request body** (no multipart dependency) and is a dry run unless
`?commit=true`.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response

from app.api.deps import get_export_service, require_token
from app.api.errors import ProblemException
from app.schemas.exports import ImportReport
from app.services.exports import ExportService

router = APIRouter(prefix="/exports", tags=["exports"], dependencies=[Depends(require_token)])

_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.get("/xlsx")
def export_xlsx(
    service: Annotated[ExportService, Depends(get_export_service)],
) -> Response:
    filename, data = service.export_xlsx()
    return Response(
        content=data,
        media_type=_XLSX,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/import", response_model=ImportReport)
async def import_xlsx(
    request: Request,
    service: Annotated[ExportService, Depends(get_export_service)],
    filename: Annotated[str, Query(description="just for the audit record")] = "upload.xlsx",
    commit: Annotated[bool, Query(description="false = dry run (default)")] = False,
) -> ImportReport:
    body = await request.body()
    if not body:
        raise ProblemException(
            status=422,
            title="Unprocessable Entity",
            detail="send the .xlsx as the raw request body (e.g. curl --data-binary @file.xlsx)",
        )
    return service.import_xlsx(filename=filename, data=body, commit=commit)
