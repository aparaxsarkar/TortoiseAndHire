"""Liveness endpoint.

`GET /api/v1/health` answers "is the process up and serving?" — nothing more.
A readiness check (`/health/ready`, which also pings the database) is added
with the DB layer on Day 3.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "tortoiseandhire"}
