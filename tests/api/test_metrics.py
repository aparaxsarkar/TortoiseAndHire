"""`GET /metrics` - Prometheus text, protected (ADR-0008). No DB needed."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import create_app

TOKEN = "s3cr3t-test-token"


@pytest.fixture(autouse=True)
def _token_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TORTOISEANDHIRE_API_TOKEN", TOKEN)


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


def test_metrics_requires_the_token(client: TestClient) -> None:
    assert client.get("/api/v1/metrics").status_code == 401


def test_metrics_renders_prometheus_text(client: TestClient) -> None:
    client.get("/api/v1/health")  # one data point via TimingMiddleware

    resp = client.get("/api/v1/metrics", headers={"Authorization": f"Bearer {TOKEN}"})

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/plain")
    assert "http_requests_total" in resp.text
    assert "http_request_duration_seconds_count" in resp.text
