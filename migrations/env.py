"""Alembic environment.

The URL comes from app settings (DATABASE_URL), not alembic.ini. Importing
`app.models` registers every table on `Base.metadata`, which is the
autogenerate target.
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine

import app.models  # noqa: F401  -- side effect: populates Base.metadata
from app.core.config import get_settings
from app.db.base import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# created_at/updated_at use server_default=now(); comparing server defaults
# across dialects is noisy and low-value, so autogenerate skips it. Column
# types, nullability, constraints and indexes are all still compared.
_CONFIGURE = {
    "target_metadata": target_metadata,
    "compare_type": True,
    "compare_server_default": False,
}


def _url() -> str:
    return get_settings().database_url


def run_migrations_offline() -> None:
    context.configure(
        url=_url(), literal_binds=True, dialect_opts={"paramstyle": "named"}, **_CONFIGURE
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(_url(), future=True)
    with engine.connect() as connection:
        context.configure(connection=connection, **_CONFIGURE)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
