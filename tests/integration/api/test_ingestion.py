"""`POST/GET /ingestion/*` against real Postgres, with a fake (no-network) adapter."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import get_ingestion_service
from app.discovery.ruleset import Ruleset
from app.main import create_app
from app.models import Source
from app.services.ingestion import IngestionService
from tests.unit.ingestion.fakes import RULESET_KW, FakeSource, sample_run_postings

RULESET = Ruleset(**RULESET_KW)
TOKEN = "s3cr3t-test-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


@contextmanager
def _use(session: Session) -> Iterator[Session]:
    yield session


@pytest.fixture(autouse=True)
def _token_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TORTOISEANDHIRE_API_TOKEN", TOKEN)


@pytest.fixture
def client(db_session: Session) -> TestClient:
    app = create_app()

    def factory(slug: str) -> FakeSource:
        return FakeSource(sample_run_postings(), slug=slug)

    app.dependency_overrides[get_ingestion_service] = lambda: IngestionService(
        session_factory=lambda: _use(db_session), source_factory=factory, ruleset=RULESET
    )
    return TestClient(app)


def _seed_source(session: Session) -> Source:
    src = Source(slug=f"greenhouse-{uuid.uuid4()}", display_name="Greenhouse")
    session.add(src)
    session.flush()
    return src


def test_trigger_a_run_for_one_source(client: TestClient, db_session: Session) -> None:
    src = _seed_source(db_session)
    resp = client.post(
        "/api/v1/ingestion/runs", headers=AUTH, json={"source": src.slug, "targets": ["acme"]}
    )
    assert resp.status_code == 200
    results = resp.json()["results"]
    assert len(results) == 1
    assert results[0]["status"] == "success"
    assert results[0]["inserted"] == 2
    assert results[0]["filtered_out"] == 1


def test_trigger_with_a_plan(client: TestClient, db_session: Session) -> None:
    src = _seed_source(db_session)
    resp = client.post("/api/v1/ingestion/runs", headers=AUTH, json={"plan": {src.slug: ["acme"]}})
    assert resp.status_code == 200
    assert [r["status"] for r in resp.json()["results"]] == ["success"]


def test_history_endpoints(client: TestClient, db_session: Session) -> None:
    src = _seed_source(db_session)
    client.post(
        "/api/v1/ingestion/runs", headers=AUTH, json={"source": src.slug, "targets": ["acme"]}
    )

    listing = client.get("/api/v1/ingestion/runs", headers=AUTH)
    assert listing.status_code == 200
    runs = listing.json()
    assert len(runs) == 1
    assert runs[0]["source"] == src.slug
    assert runs[0]["status"] == "success"
    assert runs[0]["trigger"] == "manual_api"
    assert runs[0]["stats"]["inserted"] == 2

    run_id = runs[0]["id"]
    one = client.get(f"/api/v1/ingestion/runs/{run_id}", headers=AUTH)
    assert one.status_code == 200
    assert one.json()["id"] == run_id

    missing = client.get(f"/api/v1/ingestion/runs/{uuid.uuid4()}", headers=AUTH)
    assert missing.status_code == 404
    assert missing.headers["content-type"].startswith("application/problem+json")


def test_triggering_an_unseeded_source_is_a_409_problem(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/ingestion/runs", headers=AUTH, json={"source": "not-seeded", "targets": []}
    )
    assert resp.status_code == 409
    assert resp.headers["content-type"].startswith("application/problem+json")
    assert resp.json()["title"] == "Conflict"
