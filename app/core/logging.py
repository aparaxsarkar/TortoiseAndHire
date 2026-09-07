"""Structured logging via structlog.

`configure_logging()` is called once at startup. After that, any module does
`log = get_logger(__name__)` and emits key/value events:

    log.info("ingestion.run.finished", source="greenhouse", inserted=17)

Rendered as human-readable console lines in development and as one JSON object
per line in production (so a log aggregator can parse them).
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog

from app.core.config import Settings

# structlog's processor pipeline is dynamically typed; annotating each step
# precisely fights the stubs for no real safety gain, so this module keeps the
# pipeline as list[Any] and exposes get_logger() as -> Any.


def configure_logging(settings: Settings) -> None:
    level = getattr(logging, settings.log_level.upper(), logging.INFO)

    shared: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    renderer: Any = (
        structlog.processors.JSONRenderer()
        if settings.is_production
        else structlog.dev.ConsoleRenderer(colors=sys.stdout.isatty())
    )

    structlog.configure(
        processors=[*shared, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=False,
    )


def get_logger(*names: str) -> Any:
    return structlog.get_logger(*names)
