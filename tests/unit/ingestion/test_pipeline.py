from __future__ import annotations

import pytest

from app.discovery.ruleset import Ruleset
from app.ingestion.pipeline import PipelineError, prepare
from app.schemas.canonical import CanonicalPosting
from app.sources.errors import SourcePayloadError
from tests.unit.ingestion.fakes import RULESET_KW, FakeSource, make_raw

RULESET = Ruleset(**RULESET_KW)


def test_prepare_maps_a_relevant_posting() -> None:
    raw = make_raw(id="42", title="Software Engineer", source_url="https://x/42")
    prepared = prepare(raw, FakeSource(), RULESET)

    assert prepared.posting.source_job_id == "42"
    assert prepared.identity.dedup_key == "42"
    assert prepared.verdict.matched is True
    assert len(prepared.content_hash) == 64


def test_prepare_still_returns_an_irrelevant_posting_for_the_reject_ledger() -> None:
    raw = make_raw(id="9", title="Senior Staff Engineer", source_url="https://x/9")
    prepared = prepare(raw, FakeSource(), RULESET)

    assert prepared.verdict.matched is False
    assert "seniority_excluded" in prepared.verdict.reasons


def test_parse_source_error_becomes_a_parse_stage_pipeline_error() -> None:
    raw = make_raw(source_url="https://x/1")
    src = FakeSource(parse_map={"https://x/1": SourcePayloadError("no id")})

    with pytest.raises(PipelineError) as excinfo:
        prepare(raw, src, RULESET)
    assert excinfo.value.stage == "parse"
    assert excinfo.value.error_type == "SourcePayloadError"
    assert excinfo.value.source_ref == "https://x/1"


def test_unexpected_parser_exception_is_wrapped_not_propagated() -> None:
    raw = make_raw(source_url="https://x/1")
    src = FakeSource(parse_map={"https://x/1": KeyError("title")})

    with pytest.raises(PipelineError) as excinfo:
        prepare(raw, src, RULESET)
    assert excinfo.value.stage == "parse"
    assert excinfo.value.error_type == "KeyError"
    assert "unexpected parser error" in str(excinfo.value)


def test_missing_identity_becomes_an_identity_stage_pipeline_error() -> None:
    raw = make_raw(source_url="https://x/1")
    unusable = CanonicalPosting(
        source_slug="greenhouse",
        source_job_id=None,
        url="not-a-url",
        company_name="Acme",
        title="Software Engineer",
    )
    src = FakeSource(parse_map={"https://x/1": unusable})

    with pytest.raises(PipelineError) as excinfo:
        prepare(raw, src, RULESET)
    assert excinfo.value.stage == "identity"
    assert excinfo.value.error_type == "IdentityError"
