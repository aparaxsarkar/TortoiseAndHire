from __future__ import annotations

import structlog
from structlog.testing import capture_logs

from app.core.config import Settings
from app.core.logging import configure_logging, get_logger


def test_emits_structured_events() -> None:
    configure_logging(Settings(_env_file=None))
    with capture_logs() as logs:
        get_logger("test").info("something.happened", count=3)
    assert logs == [{"event": "something.happened", "count": 3, "log_level": "info"}]


def test_production_uses_json_renderer() -> None:
    configure_logging(Settings(_env_file=None, env="production"))
    processors = structlog.get_config()["processors"]
    assert isinstance(processors[-1], structlog.processors.JSONRenderer)


def test_development_uses_console_renderer() -> None:
    configure_logging(Settings(_env_file=None, env="development"))
    processors = structlog.get_config()["processors"]
    assert isinstance(processors[-1], structlog.dev.ConsoleRenderer)


def test_log_level_filters_below_threshold() -> None:
    configure_logging(Settings(_env_file=None, log_level="WARNING"))
    with capture_logs() as logs:
        get_logger("test").info("suppressed")
        get_logger("test").warning("kept")
    events = [entry["event"] for entry in logs]
    assert events == ["kept"]
