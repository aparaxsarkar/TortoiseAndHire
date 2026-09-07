"""Health endpoints.

- `GET /api/v1/health` - liveness: is the process up and serving?
- `GET /api/v1/health/ready` - readiness: are its dependencies (the database)
  reachable? Returns 503 if not, so a load balancer can hold traffic back.
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.services import health as health_service

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "tortoiseandhire"}


@router.get("/health/ready")
def ready() -> JSONResponse:
    result = health_service.readiness()
    code = 200 if result["status"] == "ok" else 503
    return JSONResponse(result, status_code=code)
