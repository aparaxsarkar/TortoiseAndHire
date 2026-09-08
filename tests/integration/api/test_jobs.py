"""`GET /jobs` and `GET /jobs/{id}` against real Postgres."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import get_job_service
from app.main import create_app
from app.models import Company, Job, Source, SourcePosting
from app.services.jobs import JobService

_PRIVATE_KEYS = ("application", "networking", "notes", "applied", "outcome", "networking_notes")


@contextmanager
def _use(session: Session) -> Iterator[Session]:
    yield session


@pytest.fixture
def client(db_session: Session) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_job_service] = lambda: JobService(
        session_factory=lambda: _use(db_session)
    )
    return TestClient(app)


def _seed(session: Session) -> dict[str, uuid.UUID]:
    company = Company(name="Acme", normalized_name=f"acme-{uuid.uuid4()}")
    src = Source(slug=f"greenhouse-{uuid.uuid4()}", display_name="Greenhouse")
    session.add_all([company, src])
    session.flush()
    ml = Job(
        company_id=company.id,
        title="ML Engineer",
        normalized_title="ml engineer",
        remote=True,
        status="open",
    )
    hr = Job(
        company_id=company.id,
        title="HR Partner",
        normalized_title="hr partner",
        remote=False,
        status="open",
    )
    session.add_all([ml, hr])
    session.flush()
    session.add(
        SourcePosting(
            source_id=src.id,
            job_id=ml.id,
            source_job_id="G-1",
            canonical_url="https://boards.greenhouse.io/acme/jobs/1",
            dedup_key="G-1",
            raw_payload={},
            content_hash="h",
        )
    )
    session.flush()
    return {"ml": ml.id, "hr": hr.id}


def test_list_jobs_returns_the_page(client: TestClient, db_session: Session) -> None:
    _seed(db_session)
    resp = client.get("/api/v1/jobs")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    assert {item["title"] for item in body["items"]} == {"ML Engineer", "HR Partner"}


def test_list_jobs_applies_filters(client: TestClient, db_session: Session) -> None:
    _seed(db_session)
    resp = client.get("/api/v1/jobs", params={"q": "engineer", "remote": "true"})
    body = resp.json()
    assert [item["title"] for item in body["items"]] == ["ML Engineer"]
    assert body["items"][0]["postings"][0]["url"].startswith("https://")


def test_get_job_returns_one_and_is_redacted(client: TestClient, db_session: Session) -> None:
    ids = _seed(db_session)
    resp = client.get(f"/api/v1/jobs/{ids['ml']}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["title"] == "ML Engineer"
    assert body["company_name"] == "Acme"
    for key in _PRIVATE_KEYS:
        assert key not in body


def test_get_missing_job_is_a_404_problem(client: TestClient) -> None:
    resp = client.get(f"/api/v1/jobs/{uuid.uuid4()}")
    assert resp.status_code == 404
    assert resp.headers["content-type"].startswith("application/problem+json")
    assert resp.json()["title"] == "Not Found"


def test_bad_uuid_path_is_a_422_problem(client: TestClient) -> None:
    resp = client.get("/api/v1/jobs/not-a-uuid")
    assert resp.status_code == 422
    assert resp.headers["content-type"].startswith("application/problem+json")
