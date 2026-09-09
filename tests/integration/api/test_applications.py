"""`GET`/`PATCH /jobs/{id}/application` - protected (ADR-0008, ADR-0011)."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import get_application_service
from app.main import create_app
from app.models import Company, Job
from app.services.applications import ApplicationService
from tests.integration.conftest import SessionFactory

TOKEN = "s3cr3t-test-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture(autouse=True)
def _token_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TORTOISEANDHIRE_API_TOKEN", TOKEN)


@pytest.fixture
def client(session_factory: SessionFactory) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_application_service] = lambda: ApplicationService(
        session_factory=session_factory
    )
    return TestClient(app)


def _seed_job(session: Session) -> uuid.UUID:
    company = Company(name="Acme", normalized_name=f"acme-{uuid.uuid4()}")
    session.add(company)
    session.flush()
    job = Job(company_id=company.id, title="ML Engineer", normalized_title="ml engineer")
    session.add(job)
    session.flush()
    return job.id


def test_get_requires_the_token(client: TestClient, db_session: Session) -> None:
    job_id = _seed_job(db_session)
    assert client.get(f"/api/v1/jobs/{job_id}/application").status_code == 401


def test_get_before_any_patch_is_a_404_problem(client: TestClient, db_session: Session) -> None:
    job_id = _seed_job(db_session)
    resp = client.get(f"/api/v1/jobs/{job_id}/application", headers=AUTH)
    assert resp.status_code == 404
    assert resp.headers["content-type"].startswith("application/problem+json")


def test_patch_creates_then_bumps_the_revision(client: TestClient, db_session: Session) -> None:
    job_id = _seed_job(db_session)

    first = client.patch(f"/api/v1/jobs/{job_id}/application", headers=AUTH, json={"applied": True})
    assert first.status_code == 200
    assert first.json()["revision"] == 1
    assert first.json()["applied"] is True
    assert first.json()["updated_via"] == "api"

    second = client.patch(
        f"/api/v1/jobs/{job_id}/application", headers=AUTH, json={"outcome": "screen"}
    )
    assert second.json()["revision"] == 2
    assert second.json()["outcome"] == "screen"

    got = client.get(f"/api/v1/jobs/{job_id}/application", headers=AUTH)
    assert got.json()["revision"] == 2


def test_empty_patch_is_a_422(client: TestClient, db_session: Session) -> None:
    job_id = _seed_job(db_session)
    resp = client.patch(f"/api/v1/jobs/{job_id}/application", headers=AUTH, json={})
    assert resp.status_code == 422
    assert resp.headers["content-type"].startswith("application/problem+json")


def test_patching_a_canonical_field_is_a_422(client: TestClient, db_session: Session) -> None:
    job_id = _seed_job(db_session)
    resp = client.patch(
        f"/api/v1/jobs/{job_id}/application", headers=AUTH, json={"title": "hijacked"}
    )
    assert resp.status_code == 422  # extra="forbid" on ApplicationPatch


def test_patch_on_an_unknown_job_is_a_404(client: TestClient) -> None:
    resp = client.patch(
        f"/api/v1/jobs/{uuid.uuid4()}/application", headers=AUTH, json={"applied": True}
    )
    assert resp.status_code == 404
