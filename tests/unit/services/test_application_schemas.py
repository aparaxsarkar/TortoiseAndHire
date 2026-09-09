from __future__ import annotations

from typing import get_args

import pytest
from pydantic import ValidationError

from app.models.enums import ApplicationOutcome, NetworkingStatus
from app.schemas.applications import (
    ApplicationOutcomeName,
    ApplicationPatch,
    NetworkingStatusName,
)


def test_literal_aliases_match_the_db_enums() -> None:
    assert set(get_args(NetworkingStatusName)) == {e.value for e in NetworkingStatus}
    assert set(get_args(ApplicationOutcomeName)) == {e.value for e in ApplicationOutcome}


def test_a_field_can_be_set() -> None:
    patch = ApplicationPatch(applied=True)
    assert patch.model_fields_set == {"applied"}


def test_empty_patch_is_rejected() -> None:
    with pytest.raises(ValidationError, match="at least one field"):
        ApplicationPatch()


def test_unknown_field_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ApplicationPatch.model_validate({"title": "sneaky"})


def test_bad_enum_value_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ApplicationPatch(outcome="hired")  # not a member of ApplicationOutcome


def test_clearing_a_field_to_null_is_a_real_change() -> None:
    patch = ApplicationPatch.model_validate({"notes": None})
    assert patch.model_fields_set == {"notes"}
    assert patch.model_dump(exclude_unset=True) == {"notes": None}
