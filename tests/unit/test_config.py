from __future__ import annotations

import pytest

from app.core.config import Settings, get_settings


def test_defaults() -> None:
    s = Settings(_env_file=None)
    assert s.env == "development"
    assert s.is_production is False
    assert s.metrics_enabled is True
    assert s.database_url.startswith("postgresql+psycopg://")


def test_reads_prefixed_env_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TORTOISEANDHIRE_ENV", "production")
    monkeypatch.setenv("TORTOISEANDHIRE_API_TOKEN", "secret-xyz")
    monkeypatch.setenv("TORTOISEANDHIRE_LOG_LEVEL", "DEBUG")
    s = Settings(_env_file=None)
    assert s.env == "production"
    assert s.is_production is True
    assert s.api_token == "secret-xyz"
    assert s.log_level == "DEBUG"


def test_database_url_has_no_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@host:5432/db")
    monkeypatch.delenv("TORTOISEANDHIRE_DATABASE_URL", raising=False)
    s = Settings(_env_file=None)
    assert s.database_url.endswith("@host:5432/db")


def test_invalid_env_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TORTOISEANDHIRE_ENV", "staging")
    with pytest.raises(ValueError):
        Settings(_env_file=None)


def test_get_settings_is_cached() -> None:
    assert get_settings() is get_settings()
