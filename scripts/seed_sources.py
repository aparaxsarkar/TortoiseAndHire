"""Insert the fixed `sources` rows. Idempotent - safe to re-run.

    python -m scripts.seed_sources

Run once after the first migration, and it's harmless to run again (the deploy
pre-deploy command does). Needs `DATABASE_URL`.
"""

from __future__ import annotations

from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.db.repositories import SourceRepository
from app.db.session import session_scope
from app.models import Source
from app.sources.registry import available

log = get_logger("scripts.seed_sources")


def main() -> None:
    configure_logging(get_settings())
    with session_scope() as session:
        repo = SourceRepository(session)
        for slug in available():
            if repo.get_by_slug(slug) is None:
                session.add(Source(slug=slug, display_name=slug.title()))
                log.info("seed_sources.inserted", slug=slug)
            else:
                log.info("seed_sources.exists", slug=slug)


if __name__ == "__main__":
    main()
