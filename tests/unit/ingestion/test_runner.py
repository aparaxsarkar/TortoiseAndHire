from __future__ import annotations

import pytest

from app.discovery.ruleset import Ruleset
from app.ingestion.ports import PersistOutcome
from app.ingestion.runner import IngestionRunner
from app.schemas.canonical import CanonicalPosting
from app.sources.base import SourceQuery
from app.sources.errors import SourceAuthError, SourceUnavailable
from tests.unit.ingestion.fakes import (
    RULESET_KW,
    FakeFilteredPostingSink,
    FakeRunStore,
    FakeSource,
    FakeSourcePostingSink,
    make_raw,
)

RULESET = Ruleset(**RULESET_KW)
QUERY = SourceQuery(targets=["acme"])


def _runner(
    source: FakeSource,
    run_store: FakeRunStore,
    posting_sink: FakeSourcePostingSink,
    filtered_sink: FakeFilteredPostingSink,
    **kw: object,
) -> IngestionRunner:
    return IngestionRunner(
        source=source,
        ruleset=RULESET,
        posting_sink=posting_sink,
        filtered_sink=filtered_sink,
        run_store=run_store,
        fetch_retry_backoff=0.0,
        **kw,  # type: ignore[arg-type]
    )


async def test_all_relevant_postings_are_inserted(
    run_store: FakeRunStore,
    posting_sink: FakeSourcePostingSink,
    filtered_sink: FakeFilteredPostingSink,
) -> None:
    raws = [
        make_raw(id="1", title="Software Engineer", source_url="https://x/1"),
        make_raw(id="2", title="Backend Developer", source_url="https://x/2"),
    ]
    src = FakeSource(raws)
    result = await _runner(src, run_store, posting_sink, filtered_sink).run(QUERY)

    assert (result.fetched, result.matched, result.inserted) == (2, 2, 2)
    assert result.filtered_out == 0
    assert result.failed == 0
    assert result.status == "success"
    assert run_store.started == [("greenhouse", "scheduled")]
    assert run_store.finished[-1]["status"] == "success"
    assert run_store.finished[-1]["stats"]["inserted"] == 2


async def test_irrelevant_posting_goes_to_the_filtered_sink(
    run_store: FakeRunStore,
    posting_sink: FakeSourcePostingSink,
    filtered_sink: FakeFilteredPostingSink,
) -> None:
    raws = [
        make_raw(id="1", title="Senior Staff Engineer", source_url="https://x/1"),
        make_raw(id="2", title="Software Engineer", source_url="https://x/2"),
    ]
    result = await _runner(FakeSource(raws), run_store, posting_sink, filtered_sink).run(QUERY)

    assert result.filtered_out == 1
    assert result.matched == 1
    assert result.inserted == 1
    assert [k for k, _ in filtered_sink.recorded] == ["1"]
    assert "seniority_excluded" in filtered_sink.recorded[0][1]
    assert posting_sink.persisted == ["2"]


async def test_parse_failure_is_isolated(
    run_store: FakeRunStore,
    posting_sink: FakeSourcePostingSink,
    filtered_sink: FakeFilteredPostingSink,
) -> None:
    good = make_raw(id="1", title="Software Engineer", source_url="https://x/1")
    bad = make_raw(id="2", title="Software Engineer", source_url="https://x/2")
    src = FakeSource([bad, good], parse_map={"https://x/2": ValueError("bad json")})

    result = await _runner(src, run_store, posting_sink, filtered_sink).run(QUERY)

    assert result.failed == 1
    assert result.inserted == 1
    assert result.status == "partial"
    assert run_store.errors[0].stage == "parse"
    assert run_store.errors[0].error_type == "ValueError"
    assert run_store.finished[-1]["error_summary"] == "1 posting(s) skipped"


async def test_identity_failure_is_isolated(
    run_store: FakeRunStore,
    posting_sink: FakeSourcePostingSink,
    filtered_sink: FakeFilteredPostingSink,
) -> None:
    no_identity = CanonicalPosting(
        source_slug="greenhouse",
        source_job_id=None,
        url="not-a-url",
        company_name="Acme",
        title="Software Engineer",
    )
    raw = make_raw(id="x", source_url="https://x/1")
    src = FakeSource([raw], parse_map={"https://x/1": no_identity})

    result = await _runner(src, run_store, posting_sink, filtered_sink).run(QUERY)

    assert result.failed == 1
    assert run_store.errors[0].stage == "identity"


async def test_persist_failure_is_isolated(
    run_store: FakeRunStore,
    filtered_sink: FakeFilteredPostingSink,
) -> None:
    raws = [
        make_raw(id="1", title="Software Engineer", source_url="https://x/1"),
        make_raw(id="2", title="Software Engineer", source_url="https://x/2"),
    ]
    sink = FakeSourcePostingSink(raise_on={"1"})
    result = await _runner(FakeSource(raws), run_store, sink, filtered_sink).run(QUERY)

    assert result.failed == 1
    assert result.inserted == 1
    assert result.status == "partial"
    assert run_store.errors[0].stage == "persist"
    assert run_store.errors[0].source_ref == "1"


async def test_filtered_sink_failure_is_isolated(
    run_store: FakeRunStore,
    posting_sink: FakeSourcePostingSink,
) -> None:
    raw = make_raw(id="1", title="Senior Manager", source_url="https://x/1")
    filtered_sink = FakeFilteredPostingSink(raise_on={"1"})
    result = await _runner(FakeSource([raw]), run_store, posting_sink, filtered_sink).run(QUERY)

    assert result.filtered_out == 1
    assert result.failed == 1
    assert run_store.errors[0].stage == "persist"


async def test_insert_update_unchanged_counts(
    run_store: FakeRunStore,
    filtered_sink: FakeFilteredPostingSink,
) -> None:
    raws = [
        make_raw(id="1", title="Software Engineer", source_url="https://x/1"),
        make_raw(id="2", title="Software Engineer", source_url="https://x/2"),
        make_raw(id="3", title="Software Engineer", source_url="https://x/3"),
    ]
    sink = FakeSourcePostingSink(
        outcomes={
            "1": PersistOutcome.INSERTED,
            "2": PersistOutcome.UPDATED,
            "3": PersistOutcome.UNCHANGED,
        }
    )
    result = await _runner(FakeSource(raws), run_store, sink, filtered_sink).run(QUERY)

    assert (result.inserted, result.updated, result.unchanged) == (1, 1, 1)
    assert result.status == "success"


async def test_run_is_skipped_when_the_lock_is_held(
    posting_sink: FakeSourcePostingSink,
    filtered_sink: FakeFilteredPostingSink,
) -> None:
    store = FakeRunStore(lock_granted=False)
    src = FakeSource([make_raw()])
    result = await _runner(src, store, posting_sink, filtered_sink).run(QUERY)

    assert result.status == "skipped"
    assert result.run_id is None
    assert store.started == []
    assert store.finished == []
    assert src.fetch_calls == 0


async def test_fetch_retries_transient_failures_then_succeeds(
    run_store: FakeRunStore,
    posting_sink: FakeSourcePostingSink,
    filtered_sink: FakeFilteredPostingSink,
) -> None:
    src = FakeSource(
        [make_raw(id="1", title="Software Engineer", source_url="https://x/1")],
        fail_fetch_times=2,
        fetch_exc=SourceUnavailable("503"),
    )
    result = await _runner(src, run_store, posting_sink, filtered_sink, fetch_retry_attempts=3).run(
        QUERY
    )

    assert src.fetch_calls == 3
    assert result.status == "success"
    assert result.inserted == 1


async def test_fetch_auth_error_fails_the_run_without_retrying(
    run_store: FakeRunStore,
    posting_sink: FakeSourcePostingSink,
    filtered_sink: FakeFilteredPostingSink,
) -> None:
    src = FakeSource([], fail_fetch_times=1, fetch_exc=SourceAuthError("403"))
    result = await _runner(src, run_store, posting_sink, filtered_sink, fetch_retry_attempts=3).run(
        QUERY
    )

    assert src.fetch_calls == 1
    assert result.status == "failed"
    assert result.error_summary is not None
    assert "SourceAuthError" in result.error_summary
    assert run_store.errors[0].stage == "fetch"
    assert run_store.finished[-1]["status"] == "failed"


async def test_fetch_exhausts_retries_then_fails(
    run_store: FakeRunStore,
    posting_sink: FakeSourcePostingSink,
    filtered_sink: FakeFilteredPostingSink,
) -> None:
    src = FakeSource([], fail_fetch_times=9, fetch_exc=SourceUnavailable("503"))
    result = await _runner(src, run_store, posting_sink, filtered_sink, fetch_retry_attempts=3).run(
        QUERY
    )

    assert src.fetch_calls == 3
    assert result.status == "failed"


@pytest.mark.parametrize("attempts", [1, 2])
async def test_fetch_retry_attempt_count_is_honoured(
    attempts: int,
    run_store: FakeRunStore,
    posting_sink: FakeSourcePostingSink,
    filtered_sink: FakeFilteredPostingSink,
) -> None:
    src = FakeSource([], fail_fetch_times=9, fetch_exc=SourceUnavailable("503"))
    await _runner(src, run_store, posting_sink, filtered_sink, fetch_retry_attempts=attempts).run(
        QUERY
    )
    assert src.fetch_calls == attempts
