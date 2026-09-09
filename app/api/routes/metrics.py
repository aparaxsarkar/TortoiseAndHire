"""`GET /metrics` - the in-process counters in Prometheus text format.

Protected (ADR-0008): metrics can leak request patterns, so it's behind the
token like the rest of the private surface.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse

from app.api.deps import require_token
from app.core.observability import metrics

router = APIRouter(tags=["metrics"], dependencies=[Depends(require_token)])

_PROM_CONTENT_TYPE = "text/plain; version=0.0.4; charset=utf-8"


@router.get("/metrics", response_class=PlainTextResponse)
def prometheus_metrics() -> PlainTextResponse:
    return PlainTextResponse(metrics.render_prometheus(), media_type=_PROM_CONTENT_TYPE)
