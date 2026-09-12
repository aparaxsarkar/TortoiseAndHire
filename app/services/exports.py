"""The Excel round-trip (ADR-0005 revised, ADR-0010, ADR-0013).

Export = a full snapshot of jobs + their application state. Import = keyed on the
hidden `job_id`, **dry-run by default**, and guarded by the hidden `revision`:
if the sheet's revision doesn't match the live `applications` row, that row is a
`conflict` and is skipped. A commit also writes an `application_import_runs`
audit row.

Two kinds of edit reconcile independently (ADR-0013):
- **Application** fields (`Applied` ... `Notes`) go through `write_application` -
  same path as the API `PATCH`, revision-guarded, reported as `changes`.
- **Canonical** fields (`Title`, `Company`, `URL`) write to `jobs` / `companies` /
  `source_postings` - no revision lock, reported separately as
  `canonical_changes` so an accidental edit can't hide inside a routine status
  update. `dedup_key` is never touched by this path (it's derived data, ADR-0002).
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Callable
from contextlib import AbstractContextManager

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import TortoiseError
from app.core.logging import get_logger
from app.db.repositories.applications import ApplicationRepository
from app.db.repositories.companies import CompanyRepository
from app.db.repositories.jobs import JobRepository
from app.db.repositories.source_postings import SourcePostingRepository
from app.db.session import session_scope
from app.exports.excel import ParsedRow, WorkbookError, read_workbook, write_workbook
from app.exports.layout import APPLICATION_FIELDS
from app.models import Application, ApplicationImportRun, Company, Job, SourcePosting
from app.models.enums import (
    ApplicationOutcome,
    NetworkingStatus,
    UpdatedVia,
)
from app.models.enums import (
    values as enum_values,
)
from app.schemas.applications import ApplicationPatch
from app.schemas.exports import ExportRow, ImportReport, ImportRowChange, ImportRowResult, RowAction
from app.services.applications import write_application
from app.services.ingestion import normalize_name

log = get_logger("services.exports")

SessionFactory = Callable[[], AbstractContextManager[Session]]

_ACTIONS: tuple[RowAction, ...] = ("created", "updated", "unchanged", "conflict", "error")
_NETWORKING = set(enum_values(NetworkingStatus))
_OUTCOME = set(enum_values(ApplicationOutcome))
_DEFAULTS: dict[str, object] = {
    "applied": False,
    "applied_at": None,
    "networking": NetworkingStatus.NONE.value,
    "outcome": ApplicationOutcome.NONE.value,
    "application_url": None,
    "notes": None,
}


class ExportError(TortoiseError):
    http_status = 422
    http_title = "Unprocessable Entity"


class ExportService:
    def __init__(self, *, session_factory: SessionFactory = session_scope) -> None:
        self._session_factory = session_factory

    # -- export --------------------------------------------------------------

    def export_xlsx(self) -> tuple[str, bytes]:
        with self._session_factory() as session:
            rows = self._snapshot(session)
        filename = f"tortoiseandhire-applications-{dt.date.today().isoformat()}.xlsx"
        return filename, write_workbook(rows)

    def _snapshot(self, session: Session) -> list[ExportRow]:
        jobs = session.execute(
            select(Job, Company.name)
            .join(Company, Company.id == Job.company_id)
            .order_by(Company.name, Job.title)
        ).all()
        apps = ApplicationRepository(session).by_job_id()
        links = JobRepository(session).source_links_for([job.id for job, _ in jobs])

        rows: list[ExportRow] = []
        for job, company_name in jobs:
            app = apps.get(job.id)
            job_links = links.get(job.id) or []
            rows.append(
                ExportRow(
                    job_id=job.id,
                    title=job.title,
                    company_name=company_name,
                    url=job_links[0][1] if job_links else None,
                    applied=app.applied if app else False,
                    applied_at=app.applied_at if app else None,
                    networking=app.networking if app else NetworkingStatus.NONE.value,
                    outcome=app.outcome if app else ApplicationOutcome.NONE.value,
                    application_url=app.application_url if app else None,
                    notes=app.notes if app else None,
                    revision=app.revision if app else 0,
                )
            )
        return rows

    # -- import --------------------------------------------------------------

    def import_xlsx(self, *, filename: str, data: bytes, commit: bool = False) -> ImportReport:
        try:
            parsed = read_workbook(data)
        except WorkbookError as exc:
            raise ExportError(str(exc)) from exc

        with self._session_factory() as session:
            jobs = JobRepository(session)
            postings = SourcePostingRepository(session)
            apps = ApplicationRepository(session)
            existing = apps.by_job_id()

            results = [
                self._reconcile_row(session, jobs, postings, existing, row, commit=commit)
                for row in parsed
            ]
            counts: dict[RowAction, int] = {
                a: sum(1 for r in results if r.action == a) for a in _ACTIONS
            }
            canonical_change_count = sum(1 for r in results if r.canonical_changes)
            if commit:
                session.add(
                    ApplicationImportRun(
                        filename=filename,
                        committed=True,
                        stats={**counts, "canonical_changes": canonical_change_count},
                        report=[r.model_dump(mode="json") for r in results],
                    )
                )
                session.flush()
            report = ImportReport(
                filename=filename,
                committed=commit,
                counts=counts,
                canonical_change_count=canonical_change_count,
                rows=results,
            )

        applied = counts["created"] + counts["updated"]
        log.info(
            "exports.import.done",
            filename=filename,
            committed=commit,
            applied=applied,
            conflicts=counts["conflict"],
            errors=counts["error"],
            canonical_changes=canonical_change_count,
        )
        return report

    def _reconcile_row(
        self,
        session: Session,
        jobs: JobRepository,
        postings: SourcePostingRepository,
        existing: dict[uuid.UUID, Application],
        row: ParsedRow,
        *,
        commit: bool,
    ) -> ImportRowResult:
        if row.parse_error is not None:
            return ImportRowResult(row=row.excel_row, action="error", message=row.parse_error)
        if not row.job_id:
            return ImportRowResult(
                row=row.excel_row, action="error", message="no job_id in this row"
            )
        try:
            job_id = uuid.UUID(row.job_id)
        except ValueError:
            return ImportRowResult(
                row=row.excel_row, action="error", message=f"{row.job_id!r} is not a job id"
            )

        found = jobs.get_with_company(job_id)
        if found is None:
            return ImportRowResult(
                row=row.excel_row,
                job_id=job_id,
                action="error",
                message="no such job (was it deleted, or is this the wrong sheet?)",
            )
        job, company_name = found

        bad = self._bad_enum(row.values)
        if bad is not None:
            return ImportRowResult(row=row.excel_row, job_id=job_id, action="error", message=bad)

        app = existing.get(job_id)
        live_revision = app.revision if app is not None else 0
        if row.revision is not None and row.revision != live_revision:
            return ImportRowResult(
                row=row.excel_row,
                job_id=job_id,
                action="conflict",
                message=(
                    f"sheet revision {row.revision} != current {live_revision}; "
                    "the record changed since you exported - re-export and redo this row"
                ),
            )

        job_postings = postings.list_for_job(job_id)
        changes = self._diff(app, row.values)
        canonical_changes, note = self._canonical_diff(job, company_name, job_postings, row.values)

        action: RowAction = "unchanged"
        if changes:
            action = "created" if app is None else "updated"

        result = ImportRowResult(
            row=row.excel_row,
            job_id=job_id,
            action=action,
            changes=changes,
            canonical_changes=canonical_changes,
            message=note,
        )
        if not changes and not canonical_changes:
            return result

        if commit:
            if changes:
                app_values = {k: v for k, v in row.values.items() if k in APPLICATION_FIELDS}
                patch = ApplicationPatch.model_validate(app_values)
                write_application(session, job_id, patch, via=UpdatedVia.EXCEL_IMPORT.value)
            if canonical_changes:
                self._apply_canonical(session, job, job_postings, canonical_changes)
        return result

    @staticmethod
    def _bad_enum(values: dict[str, object]) -> str | None:
        if values.get("networking") not in _NETWORKING:
            return f"networking {values.get('networking')!r} is not one of {sorted(_NETWORKING)}"
        if values.get("outcome") not in _OUTCOME:
            return f"outcome {values.get('outcome')!r} is not one of {sorted(_OUTCOME)}"
        return None

    @staticmethod
    def _diff(app: Application | None, values: dict[str, object]) -> list[ImportRowChange]:
        changes: list[ImportRowChange] = []
        for field_name in APPLICATION_FIELDS:
            new = values[field_name]
            old = getattr(app, field_name) if app is not None else _DEFAULTS[field_name]
            if _norm(old) != _norm(new):
                changes.append(
                    ImportRowChange(field=field_name, old=_jsonable(old), new=_jsonable(new))
                )
        return changes

    @staticmethod
    def _canonical_diff(
        job: Job,
        company_name: str,
        job_postings: list[SourcePosting],
        values: dict[str, object],
    ) -> tuple[list[ImportRowChange], str | None]:
        """Title/Company/URL vs. the live record (ADR-0013). `note` carries a
        non-fatal explanation - e.g. why a URL edit couldn't be applied -
        without failing the row."""
        changes: list[ImportRowChange] = []
        note: str | None = None

        new_title = values.get("title")
        if isinstance(new_title, str) and new_title != job.title:
            changes.append(ImportRowChange(field="title", old=job.title, new=new_title))

        new_company = values.get("company_name")
        if isinstance(new_company, str) and new_company != company_name:
            changes.append(ImportRowChange(field="company_name", old=company_name, new=new_company))

        new_url = values.get("url")
        if isinstance(new_url, str):
            current_url = job_postings[0].canonical_url if job_postings else None
            if new_url != current_url:
                if len(job_postings) == 1:
                    changes.append(ImportRowChange(field="url", old=current_url, new=new_url))
                else:
                    note = (
                        f"URL change ignored: this job has {len(job_postings)} linked "
                        "posting(s), not exactly 1 - edit the source directly"
                    )

        return changes, note

    @staticmethod
    def _apply_canonical(
        session: Session,
        job: Job,
        job_postings: list[SourcePosting],
        changes: list[ImportRowChange],
    ) -> None:
        """The only place Excel writes to `jobs`/`companies`/`source_postings` -
        never `dedup_key`, which stays derived from `source_job_id` (ADR-0002)."""
        by_field = {change.field: change.new for change in changes}
        if "title" in by_field:
            job.title = by_field["title"]
            job.normalized_title = normalize_name(by_field["title"])
        if "company_name" in by_field:
            new_name = by_field["company_name"]
            company = CompanyRepository(session).get_or_create(
                normalized_name=normalize_name(new_name), name=new_name
            )
            job.company_id = company.id
        if "url" in by_field and len(job_postings) == 1:
            job_postings[0].canonical_url = by_field["url"]
        session.flush()


def _norm(value: object) -> object:
    if isinstance(value, dt.datetime):
        return value.astimezone(dt.UTC).replace(microsecond=0)
    return value


def _jsonable(value: object) -> object:
    if isinstance(value, dt.datetime):
        return value.isoformat()
    return value
