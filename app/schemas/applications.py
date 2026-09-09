"""DTOs for the private application record.

`ApplicationPatch` is the "typed patch object" from ADR-0011: it carries *only*
user-owned fields, so a canonical `jobs` field can't be written through it. The
`Literal` enum aliases mirror `app.models.enums` (a unit test pins them together)
so the schema layer stays free of SQLAlchemy imports.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

NetworkingStatusName = Literal["none", "in_progress", "contact_made", "referral"]
ApplicationOutcomeName = Literal[
    "none", "oa", "screen", "onsite", "offer", "rejected", "withdrawn", "ghosted"
]


class ApplicationPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    applied: bool | None = None
    applied_at: dt.datetime | None = None
    networking: NetworkingStatusName | None = None
    networking_notes: str | None = None
    outcome: ApplicationOutcomeName | None = None
    application_url: str | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def _at_least_one_field(self) -> ApplicationPatch:
        if not self.model_fields_set:
            raise ValueError("provide at least one field to update")
        return self


class ApplicationView(BaseModel):
    job_id: uuid.UUID
    applied: bool
    applied_at: dt.datetime | None = None
    networking: str
    networking_notes: str | None = None
    outcome: str
    application_url: str | None = None
    notes: str | None = None
    revision: int
    updated_via: str
    updated_at: dt.datetime
