"""ADR-0008: `/ingestion/*` needs the bearer token; `/jobs` does not. No DB needed."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_job_service
from app.main import create_app
from app.schemas.jobs import JobFilters, JobSearchResult

TOKEN = "s3cr3t-test-token"


class _StubJobService:
    def search(self, filters: JobFilters) -> JobSearchResult:
        return JobSearchResult(total=0, limit=filters.limit, offset=filters.offset, items=[])


@pytest.fixture(autouse=True)
def _token_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TORTOISEANDHIRE_API_TOKEN", TOKEN)


@pytest.fixture
def client() -> TestClient:
    app = create_app()
    app.dependency_overrides[get_job_service] = _StubJobService
    return TestClient(app)


PROTECTED = [
    ("post", "/api/v1/ingestion/runs"),
    ("get", "/api/v1/ingestion/runs"),
    ("get", "/api/v1/ingestion/runs/6f9619ff-8b86-d011-b42d-00cf4fc964ff"),
]


@pytest.mark.parametrize(("method", "path"), PROTECTED)
def test_protected_routes_401_without_a_token(client: TestClient, method: str, path: str) -> None:
    # a valid body, so a 401 can only come from the missing token
    resp = client.request(method, path, json={"source": "greenhouse", "targets": []})
    assert resp.status_code == 401
    assert resp.headers["content-type"].startswith("application/problem+json")
    body = resp.json()
    assert body["status"] == 401
    assert body["title"] == "Unauthorized"


def test_protected_route_401_with_the_wrong_token(client: TestClient) -> None:
    resp = client.get("/api/v1/ingestion/runs", headers={"Authorization": "Bearer nope"})
    assert resp.status_code == 401


def test_jobs_route_is_public(client: TestClient) -> None:
    resp = client.get("/api/v1/jobs")
    assert resp.status_code == 200
    assert resp.json() == {"total": 0, "limit": 50, "offset": 0, "items": []}
