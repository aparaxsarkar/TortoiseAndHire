"""The Excel round-trip (ADR-0005 revised, ADR-0010).

Export = a full snapshot of jobs + their application state. Import = keyed on the
hidden `job_id`, scoped to the editable columns, **dry-run by default**, and
guarded by the hidden `revision`: if the sheet's revision doesn't match the live
row, that row is a `conflict` and is skipped. A commit also writes an
`application_import_runs` audit row.
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
from app.db.repositories.jobs import JobRepository
from app.db.session import session_scope
from app.exports.excel import ParsedRow, WorkbookError, read_workbook, write_workbook
from app.exports.layout import EDITABLE_FIELDS
from app.models import Application, ApplicationImportRun, Company, Job
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
            apps = ApplicationRepository(session)
            existing = apps.by_job_id()

            results = [
                self._reconcile_row(session, jobs, existing, row, commit=commit) for row in parsed
            ]
            counts: dict[RowAction, int] = {
                a: sum(1 for r in results if r.action == a) for a in _ACTIONS
            }
            if commit:
                session.add(
                    ApplicationImportRun(
                        filename=filename,
                        committed=True,
                        stats=dict(counts),
                        report=[r.model_dump(mode="json") for r in results],
                    )
                )
                session.flush()
            report = ImportReport(filename=filename, committed=commit, counts=counts, rows=results)

        applied = counts["created"] + counts["updated"]
        log.info(
            "exports.import.done",
            filename=filename,
            committed=commit,
            applied=applied,
            conflicts=counts["conflict"],
            errors=counts["error"],
        )
        return report

    def _reconcile_row(
        self,
        session: Session,
        jobs: JobRepository,
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

        result = ImportRowResult(row=row.excel_row, job_id=job_id, action="error")

        if jobs.get(job_id) is None:
            result.message = "no such job (was it deleted, or is this the wrong sheet?)"
            return result

        bad = self._bad_enum(row.values)
        if bad is not None:
            result.message = bad
            return result

        app = existing.get(job_id)
        live_revision = app.revision if app is not None else 0
        if row.revision is not None and row.revision != live_revision:
            result.action = "conflict"
            result.message = (
                f"sheet revision {row.revision} != current {live_revision}; "
                "the record changed since you exported - re-export and redo this row"
            )
            return result

        changes = self._diff(app, row.values)
        if not changes:
            result.action = "unchanged"
            return result

        result.changes = changes
        result.action = "created" if app is None else "updated"
        if commit:
            patch = ApplicationPatch.model_validate(dict(row.values))
            write_application(session, job_id, patch, via=UpdatedVia.EXCEL_IMPORT.value)
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
        for field_name in EDITABLE_FIELDS:
            new = values[field_name]
            old = getattr(app, field_name) if app is not None else _DEFAULTS[field_name]
            if _norm(old) != _norm(new):
                changes.append(
                    ImportRowChange(field=field_name, old=_jsonable(old), new=_jsonable(new))
                )
        return changes


def _norm(value: object) -> object:
    if isinstance(value, dt.datetime):
        return value.astimezone(dt.UTC).replace(microsecond=0)
    return value


def _jsonable(value: object) -> object:
    if isinstance(value, dt.datetime):
        return value.isoformat()
    return value
