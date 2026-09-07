"""Health checks. Keeps the API layer from importing `db/` directly - the route
asks this, this asks the database.
"""

from __future__ import annotations

from app.db.session import check_database


def readiness() -> dict[str, str]:
    """Liveness plus dependency checks. Extend as dependencies are added."""
    database_ok = check_database()
    return {
        "status": "ok" if database_ok else "degraded",
        "database": "ok" if database_ok else "error",
    }
