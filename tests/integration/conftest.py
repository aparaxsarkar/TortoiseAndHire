"""Database fixtures for integration tests.

These need a real Postgres. When `DATABASE_URL` is not a reachable
`postgresql://` URL (the default on a local machine without one), every test
in `tests/integration/` skips itself - CI provides the service.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, Engine, create_engine
from sqlalchemy.orm import Session

from app.core.config import get_settings

SessionFactory = Callable[[], AbstractContextManager[Session]]


def _postgres_available(url: str) -> bool:
    if not url.startswith("postgresql"):
        return False
    try:
        create_engine(url).connect().close()
        return True
    except Exception:
        return False


@pytest.fixture(scope="session")
def db_url() -> str:
    url = get_settings().database_url
    if not _postgres_available(url):
        pytest.skip("no reachable Postgres (set DATABASE_URL to run integration tests)")
    return url


@pytest.fixture(scope="session")
def migrated_engine(db_url: str) -> Iterator[Engine]:
    engine = create_engine(db_url, future=True)
    cfg = Config("alembic.ini")
    command.upgrade(cfg, "head")  # idempotent if already at head
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(migrated_engine: Engine) -> Iterator[Session]:
    """A session wrapped in a transaction that is rolled back after each test,
    so tests never see each other's rows."""
    connection = migrated_engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, expire_on_commit=False)
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def raw_connection(migrated_engine: Engine) -> Iterator[Connection]:
    """A plain connection for schema introspection queries (pg_catalog etc.)."""
    with migrated_engine.connect() as conn:
        yield conn


@pytest.fixture
def session_factory(db_session: Session) -> SessionFactory:
    """A `session_factory` that hands services the test's rolled-back session and
    neither commits nor closes it - lets `IngestionService(...)` / `JobService(...)`
    / etc. run against the same transaction the test seeds into."""

    @contextmanager
    def _factory() -> Iterator[Session]:
        yield db_session

    return _factory
