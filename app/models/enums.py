"""Closed value sets used by the schema.

Each is stored as plain text with a DB `CHECK` constraint (see `enum_check`),
not a Postgres native ENUM type — native enums are painful to alter later. The
Python enum is the single source of truth; the Pydantic schemas (day 4+) reuse
these same classes.
"""

from __future__ import annotations

import enum

from sqlalchemy import CheckConstraint


class JobStatus(str, enum.Enum):
    OPEN = "open"
    CLOSED = "closed"
    UNKNOWN = "unknown"


class RunStatus(str, enum.Enum):
    RUNNING = "running"
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"
    SKIPPED = "skipped"


class RunTrigger(str, enum.Enum):
    MANUAL_API = "manual_api"
    CLI = "cli"
    SCHEDULED = "scheduled"


class NetworkingStatus(str, enum.Enum):
    NONE = "none"
    IN_PROGRESS = "in_progress"
    CONTACT_MADE = "contact_made"
    REFERRAL = "referral"


class ApplicationOutcome(str, enum.Enum):
    NONE = "none"
    OA = "oa"
    SCREEN = "screen"
    ONSITE = "onsite"
    OFFER = "offer"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"
    GHOSTED = "ghosted"


class UpdatedVia(str, enum.Enum):
    API = "api"
    ADMIN_UI = "admin_ui"
    EXCEL_IMPORT = "excel_import"


class IngestionStage(str, enum.Enum):
    FETCH = "fetch"
    PARSE = "parse"
    VALIDATE = "validate"
    IDENTITY = "identity"
    RELEVANCE = "relevance"
    PERSIST = "persist"


def values(e: type[enum.Enum]) -> tuple[str, ...]:
    return tuple(str(member.value) for member in e)


def enum_check(column: str, e: type[enum.Enum], name: str) -> CheckConstraint:
    """A `CHECK (column IN (...))` constraint listing every member of `e`."""
    allowed = ", ".join(f"'{v}'" for v in values(e))
    return CheckConstraint(f"{column} IN ({allowed})", name=name)
