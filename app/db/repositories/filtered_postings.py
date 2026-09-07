from __future__ import annotations

from typing import Any

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models import FilteredPosting


class FilteredPostingRepository:
    """Writes the reject ledger (ADR-0009). Same `(source_id, dedup_key)`
    idempotency as `source_postings`; a re-seen reject just bumps `last_seen_at`
    and refreshes the reasons/ruleset it was last judged against.
    """

    def __init__(self, session: Session) -> None:
        self.session = session

    def upsert(
        self,
        *,
        source_id: int,
        source_job_id: str | None,
        canonical_url: str,
        dedup_key: str,
        title: str | None,
        company_name: str | None,
        reasons: list[str],
        ruleset_version: str,
        raw_payload: dict[str, Any] | None = None,
    ) -> None:
        mutable = {
            "source_job_id": source_job_id,
            "canonical_url": canonical_url,
            "title": title,
            "company_name": company_name,
            "reasons": reasons,
            "ruleset_version": ruleset_version,
            "raw_payload": raw_payload,
        }
        stmt = (
            pg_insert(FilteredPosting)
            .values({"source_id": source_id, "dedup_key": dedup_key, **mutable})
            .on_conflict_do_update(
                index_elements=["source_id", "dedup_key"],
                set_={**mutable, "last_seen_at": func.now()},
            )
        )
        self.session.execute(stmt)
