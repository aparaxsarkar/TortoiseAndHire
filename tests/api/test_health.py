from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.observability import metrics
from app.main import create_app


def test_health_returns_200_ok() -> None:
    client = TestClient(create_app())
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "service": "tortoiseandhire"}


def test_request_is_recorded_by_timing_middleware() -> None:
    client = TestClient(create_app())
    client.get("/api/v1/health")
    out = metrics.render_prometheus()
    assert 'http_requests_total{method="GET",status="200"} 1.0' in out
    assert "http_request_duration_seconds_count 1" in out
