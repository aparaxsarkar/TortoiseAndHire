"""Day-1 smoke test: proves pytest collects and runs against this tree."""

from __future__ import annotations

import app


def test_app_package_imports() -> None:
    assert app is not None
