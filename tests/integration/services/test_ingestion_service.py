"""`IngestionService` against a real database, with a fake (no-network) adapter."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.discovery.ruleset import Ruleset
from app.models import IngestionRun, Job, Source
from app.services.ingestion import IngestionService, IngestionSetupError
from tests.unit.ingestion.fakes import RULESET_KW, FakeSource, sample_run_postings

RULESET = Ruleset(**RULESET_KW)


@contextmanager
def _use(session: Session) -> Iterator[Session]:
    """A session_factory that hands back the test's rolled-back session and
    neither commits nor closes it."""
    yield session


def _service(db_session: Session, made: list[FakeSource]) -> IngestionService:
    def factory(slug: str) -> FakeSource:
        src = FakeSource(sample_run_postings(), slug=slug)
        made.append(src)
        return src

    return IngestionService(
        session_factory=lambda: _use(db_session),
        source_factory=factory,
        ruleset=RULESET,
    )


def _seed_source(session: Session) -> Source:
    src = Source(slug=f"greenhouse-{uuid.uuid4()}", display_name="Greenhouse")
    session.add(src)
    session.flush()
    return src


async def test_run_source_executes_a_run_and_returns_a_dto(db_session: Session) -> None:
    src_row = _seed_source(db_session)
    made: list[FakeSource] = []

    dto = await _service(db_session, made).run_source(src_row.slug, targets=["acme"], trigger="cli")

    assert dto.source == src_row.slug
    assert dto.status == "success"
    assert (dto.inserted, dto.filtered_out, dto.matched) == (2, 1, 2)
    assert dto.run_id is not None
    assert made[0].closed is True  # the service owns the adapter lifecycle

    assert db_session.execute(select(func.count()).select_from(Job)).scalar_one() == 2
    run = db_session.execute(
        select(IngestionRun).where(IngestionRun.source_id == src_row.id)
    ).scalar_one()
    assert run.status == "success"
    assert run.trigger == "cli"


async def test_run_source_raises_when_the_source_is_not_seeded(db_session: Session) -> None:
    made: list[FakeSource] = []
    service = _service(db_session, made)

    with pytest.raises(IngestionSetupError):
        await service.run_source("greenhouse-unseeded", targets=["acme"])

    assert made[0].closed is True  # still cleaned up on the failure path


async def test_run_all_covers_every_source_in_the_plan(db_session: Session) -> None:
    first = _seed_source(db_session)
    second = _seed_source(db_session)
    made: list[FakeSource] = []

    report = await _service(db_session, made).run_all(
        plan={first.slug: ["acme"], second.slug: ["acme"]}, trigger="scheduled"
    )

    assert {r.source for r in report.results} == {first.slug, second.slug}
    assert {r.status for r in report.results} == {"success"}
    assert all(r.inserted == 2 for r in report.results)
    assert db_session.execute(select(func.count()).select_from(Job)).scalar_one() == 4
