"""`JobService.search` / `.get` against a real database."""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy.orm import Session

from app.models import Company, Job, Source, SourcePosting
from app.schemas.jobs import JobFilters
from app.services.jobs import JobService

_NOW = dt.datetime(2026, 9, 8, tzinfo=dt.UTC)


@contextmanager
def _use(session: Session) -> Iterator[Session]:
    yield session


def _svc(session: Session) -> JobService:
    return JobService(session_factory=lambda: _use(session))


def _seed(session: Session) -> dict[str, uuid.UUID]:
    company = Company(name="Acme Robotics", normalized_name=f"acme-robotics-{uuid.uuid4()}")
    other = Company(name="Globex", normalized_name=f"globex-{uuid.uuid4()}")
    gh = Source(slug=f"greenhouse-{uuid.uuid4()}", display_name="Greenhouse")
    lever = Source(slug=f"lever-{uuid.uuid4()}", display_name="Lever")
    session.add_all([company, other, gh, lever])
    session.flush()

    ml = Job(
        company_id=company.id,
        title="Machine Learning Engineer",
        normalized_title="machine learning engineer",
        remote=True,
        status="open",
        posted_at=_NOW - dt.timedelta(days=1),
    )
    backend = Job(
        company_id=company.id,
        title="Backend Engineer",
        normalized_title="backend engineer",
        remote=False,
        status="open",
        posted_at=_NOW - dt.timedelta(days=5),
    )
    closed = Job(
        company_id=other.id,
        title="Data Engineer",
        normalized_title="data engineer",
        remote=True,
        status="closed",
        posted_at=None,
    )
    session.add_all([ml, backend, closed])
    session.flush()

    session.add_all(
        [
            SourcePosting(
                source_id=gh.id,
                job_id=ml.id,
                source_job_id="G-1",
                canonical_url="https://boards.greenhouse.io/acme/jobs/1",
                dedup_key="G-1",
                raw_payload={},
                content_hash="h1",
            ),
            SourcePosting(
                source_id=lever.id,
                job_id=ml.id,
                source_job_id="L-1",
                canonical_url="https://jobs.lever.co/acme/1",
                dedup_key="L-1",
                raw_payload={},
                content_hash="h2",
            ),
            SourcePosting(
                source_id=gh.id,
                job_id=backend.id,
                source_job_id="G-2",
                canonical_url="https://boards.greenhouse.io/acme/jobs/2",
                dedup_key="G-2",
                raw_payload={},
                content_hash="h3",
            ),
        ]
    )
    session.flush()
    return {"ml": ml.id, "backend": backend.id, "closed": closed.id, "lever_slug": lever.slug}


async def test_search_orders_by_posted_at_desc_nulls_last(db_session: Session) -> None:
    ids = _seed(db_session)
    result = _svc(db_session).search(JobFilters())

    assert result.total == 3
    assert [i.id for i in result.items] == [ids["ml"], ids["backend"], ids["closed"]]


async def test_search_filters_by_title_substring(db_session: Session) -> None:
    _seed(db_session)
    result = _svc(db_session).search(JobFilters(q="engineer"))
    assert {i.title for i in result.items} == {
        "Machine Learning Engineer",
        "Backend Engineer",
        "Data Engineer",
    }
    result = _svc(db_session).search(JobFilters(q="machine learning"))
    assert [i.title for i in result.items] == ["Machine Learning Engineer"]


async def test_search_filters_by_remote_status_and_company(db_session: Session) -> None:
    _seed(db_session)
    svc = _svc(db_session)

    assert {i.title for i in svc.search(JobFilters(remote=True)).items} == {
        "Machine Learning Engineer",
        "Data Engineer",
    }
    assert [i.title for i in svc.search(JobFilters(status="closed")).items] == ["Data Engineer"]
    assert {i.title for i in svc.search(JobFilters(company="acme")).items} == {
        "Machine Learning Engineer",
        "Backend Engineer",
    }


async def test_search_filters_by_source_slug(db_session: Session) -> None:
    ids = _seed(db_session)
    result = _svc(db_session).search(JobFilters(source=ids["lever_slug"]))
    assert [i.id for i in result.items] == [ids["ml"]]


async def test_search_paginates(db_session: Session) -> None:
    _seed(db_session)
    page = _svc(db_session).search(JobFilters(limit=1, offset=1))
    assert page.total == 3
    assert len(page.items) == 1
    assert page.items[0].title == "Backend Engineer"


async def test_summary_carries_company_name_and_source_links(db_session: Session) -> None:
    _seed(db_session)
    result = _svc(db_session).search(JobFilters(q="machine learning"))
    ml = result.items[0]

    assert ml.company_name == "Acme Robotics"
    assert ml.remote is True
    assert sorted(p.source.split("-")[0] for p in ml.postings) == ["greenhouse", "lever"]
    assert all(p.url.startswith("https://") for p in ml.postings)


async def test_get_returns_one_job_or_none(db_session: Session) -> None:
    ids = _seed(db_session)
    svc = _svc(db_session)

    found = svc.get(ids["backend"])
    assert found is not None
    assert found.title == "Backend Engineer"
    assert found.company_name == "Acme Robotics"

    assert svc.get(uuid.uuid4()) is None
