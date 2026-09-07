"""The per-posting transform: one `RawPosting` in, one `PreparedPosting` out.

Pure and synchronous - `parse -> derive identity -> evaluate relevance -> hash`.
Any stage that can't complete raises `PipelineError` tagged with the stage that
failed, so the runner can record it against exactly one posting and move on
(ADR-0004's fetch/parse split is what makes that attribution possible).
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.errors import TortoiseError
from app.deduplication.identity import IdentityError, PostingIdentity, content_hash, derive
from app.discovery.rules import RelevanceVerdict, evaluate
from app.discovery.ruleset import Ruleset
from app.ingestion.results import Stage
from app.schemas.canonical import CanonicalPosting, RawPosting
from app.sources.base import JobSource
from app.sources.errors import SourceError


class PipelineError(TortoiseError):
    def __init__(
        self,
        stage: Stage,
        message: str,
        *,
        source_ref: str | None = None,
        error_type: str = "PipelineError",
    ) -> None:
        super().__init__(message)
        self.stage: Stage = stage
        self.source_ref = source_ref
        self.error_type = error_type


@dataclass(frozen=True, slots=True)
class PreparedPosting:
    posting: CanonicalPosting
    identity: PostingIdentity
    verdict: RelevanceVerdict
    content_hash: str


def prepare(raw: RawPosting, source: JobSource, ruleset: Ruleset) -> PreparedPosting:
    ref = raw.source_url or None

    try:
        posting = source.parse(raw)
    except SourceError as exc:
        raise PipelineError(
            "parse", str(exc), source_ref=ref, error_type=type(exc).__name__
        ) from exc
    except Exception as exc:  # a parser bug must not sink the whole run
        raise PipelineError(
            "parse",
            f"unexpected parser error: {exc}",
            source_ref=ref,
            error_type=type(exc).__name__,
        ) from exc

    try:
        identity = derive(posting)
    except IdentityError as exc:
        raise PipelineError(
            "identity", str(exc), source_ref=posting.url or ref, error_type="IdentityError"
        ) from exc

    verdict = evaluate(posting, ruleset)
    return PreparedPosting(posting, identity, verdict, content_hash(posting))
