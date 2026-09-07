"""Engine + session lifecycle.

The engine is created lazily on first use (so `import app.db.session` never
opens a connection) and cached. `session_scope()` is the core context manager -
commit on success, roll back on error, always close. `get_session()` is the
thin generator wrapper FastAPI uses as a dependency.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.core.logging import get_logger

log = get_logger("db")


@lru_cache
def get_engine() -> Engine:
    return create_engine(get_settings().database_url, pool_pre_ping=True, future=True)


@lru_cache
def _sessionmaker() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False, future=True)


@contextmanager
def session_scope() -> Iterator[Session]:
    session = _sessionmaker()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_session() -> Iterator[Session]:
    """FastAPI dependency."""
    with session_scope() as session:
        yield session


def check_database() -> bool:
    """Readiness probe: can we round-trip a trivial query? Never raises."""
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as exc:
        log.warning("db.check.failed", error=str(exc))
        return False


def dispose_engine() -> None:
    """Drop pooled connections and the cached engine (test teardown, shutdown)."""
    if get_engine.cache_info().currsize:
        get_engine().dispose()
    get_engine.cache_clear()
    _sessionmaker.cache_clear()
