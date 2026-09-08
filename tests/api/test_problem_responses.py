"""Every error path is RFC 7807 `application/problem+json`. No DB needed."""

from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_job_service
from app.main import create_app

TOKEN = "s3cr3t-test-token"


class _NeverCalledJobService:
    def search(self, *a: object, **kw: object) -> object:  # pragma: no cover
        raise AssertionError("validation should reject the request before the service")


@pytest.fixture(autouse=True)
def _token_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TORTOISEANDHIRE_API_TOKEN", TOKEN)


@pytest.fixture
def client() -> TestClient:
    app = create_app()
    app.dependency_overrides[get_job_service] = _NeverCalledJobService
    return TestClient(app)


def _assert_problem(resp: httpx.Response, status: int, title: str) -> None:
    assert resp.status_code == status
    assert resp.headers["content-type"].startswith("application/problem+json")
    body = resp.json()
    assert body["status"] == status
    assert body["title"] == title


def test_query_param_validation_is_a_422_problem(client: TestClient) -> None:
    resp = client.get("/api/v1/jobs", params={"limit": 0})
    _assert_problem(resp, 422, "Unprocessable Entity")
    assert "limit" in resp.json()["detail"]


def test_body_validation_is_a_422_problem(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/ingestion/runs",
        headers={"Authorization": f"Bearer {TOKEN}"},
        json={},  # neither `source` nor `plan`
    )
    _assert_problem(resp, 422, "Unprocessable Entity")


def test_conflicting_body_shape_is_a_422_problem(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/ingestion/runs",
        headers={"Authorization": f"Bearer {TOKEN}"},
        json={"source": "greenhouse", "plan": {}},
    )
    _assert_problem(resp, 422, "Unprocessable Entity")


def test_unknown_path_is_a_404_problem(client: TestClient) -> None:
    _assert_problem(client.get("/api/v1/nope"), 404, "Not Found")
