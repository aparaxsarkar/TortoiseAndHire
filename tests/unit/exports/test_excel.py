from __future__ import annotations

import datetime as dt
import io
import uuid

import pytest
from openpyxl import load_workbook

from app.exports.excel import (
    WorkbookError,
    _as_bool,
    _as_datetime,
    _as_url,
    read_workbook,
    write_workbook,
)
from app.exports.layout import COLUMNS, HEADERS
from app.schemas.exports import ExportRow

JOB_ID = uuid.uuid4()


def _row(**kw: object) -> ExportRow:
    base: dict[str, object] = {
        "job_id": JOB_ID,
        "title": "ML Engineer",
        "company_name": "Acme",
        "url": "https://boards.greenhouse.io/acme/1",
        "revision": 3,
    }
    base.update(kw)
    return ExportRow(**base)  # type: ignore[arg-type]


def test_headers_are_nine_visible_plus_two_hidden() -> None:
    assert len(HEADERS) == 11
    assert [c.header for c in COLUMNS if not c.hidden] == [
        "Title",
        "Company",
        "URL",
        "Applied",
        "Applied At",
        "Networking",
        "Outcome",
        "Application URL",
        "Notes",
    ]
    assert [c.header for c in COLUMNS if c.hidden] == ["job_id", "revision"]


def test_round_trips_a_row() -> None:
    when = dt.datetime(2026, 9, 1, 12, 0, 0, tzinfo=dt.UTC)  # noon = an exact Excel serial
    data = write_workbook(
        [
            _row(
                applied=True,
                applied_at=when,
                networking="referral",
                outcome="screen",
                application_url="https://acme.com/apply/1",
                notes="referred by Sam",
            )
        ]
    )
    parsed = read_workbook(data)

    assert len(parsed) == 1
    r = parsed[0]
    assert r.job_id == str(JOB_ID)
    assert r.revision == 3
    assert r.values["applied"] is True
    assert r.values["applied_at"] == when
    assert r.values["networking"] == "referral"
    assert r.values["outcome"] == "screen"
    assert r.values["application_url"] == "https://acme.com/apply/1"
    assert r.values["notes"] == "referred by Sam"
    assert r.values["title"] == "ML Engineer"
    assert r.values["company_name"] == "Acme"
    assert r.values["url"] == "https://boards.greenhouse.io/acme/1"
    assert r.parse_error is None


def test_hidden_columns_are_actually_hidden() -> None:
    data = write_workbook([_row()])
    ws = load_workbook(io.BytesIO(data))["Applications"]
    assert ws.column_dimensions["J"].hidden is True  # job_id
    assert ws.column_dimensions["K"].hidden is True  # revision
    assert ws.column_dimensions["A"].hidden is False


def test_blank_applied_cell_is_not_applied() -> None:
    data = write_workbook([_row(applied=False)])
    assert read_workbook(data)[0].values["applied"] is False


def test_a_bad_yes_no_cell_becomes_a_parse_error_not_an_exception() -> None:
    data = write_workbook([_row()])
    ws = load_workbook(io.BytesIO(data))
    ws["Applications"]["D2"] = "maybe"  # the Applied column
    buf = io.BytesIO()
    ws.save(buf)

    parsed = read_workbook(buf.getvalue())
    assert parsed[0].parse_error is not None
    assert "Applied" in parsed[0].parse_error


def test_missing_job_id_column_is_a_workbook_error() -> None:
    data = write_workbook([_row()])
    ws = load_workbook(io.BytesIO(data))
    ws["Applications"]["J1"] = "not_the_key"
    buf = io.BytesIO()
    ws.save(buf)

    with pytest.raises(WorkbookError, match="job_id"):
        read_workbook(buf.getvalue())


def test_garbage_bytes_are_a_workbook_error() -> None:
    with pytest.raises(WorkbookError):
        read_workbook(b"this is not a spreadsheet")


def test_export_with_no_rows_still_has_a_readable_header() -> None:
    assert read_workbook(write_workbook([])) == []


def test_a_blank_row_in_the_middle_is_skipped() -> None:
    data = write_workbook([_row()])
    wb = load_workbook(io.BytesIO(data))
    wb["Applications"].append([None] * len(HEADERS))  # a trailing empty row
    wb["Applications"].append([None, None, None, None, None, None, None, None, None, None, None])
    buf = io.BytesIO()
    wb.save(buf)
    assert len(read_workbook(buf.getvalue())) == 1


def test_a_workbook_with_no_rows_at_all_is_an_error() -> None:
    from openpyxl import Workbook

    buf = io.BytesIO()
    Workbook().save(buf)  # a single empty sheet, no header row
    with pytest.raises(WorkbookError, match="empty"):
        read_workbook(buf.getvalue())


@pytest.mark.parametrize(
    ("cell", "expected"),
    [
        ("yes", True),
        ("TRUE", True),
        (1, True),
        ("no", False),
        ("", False),
        (None, None),
        (0, False),
    ],
)
def test_as_bool_variants(cell: object, expected: bool | None) -> None:
    assert _as_bool(cell) == expected


def test_as_bool_rejects_garbage() -> None:
    with pytest.raises(WorkbookError):
        _as_bool("perhaps")


def test_as_datetime_variants() -> None:
    assert _as_datetime(None) is None
    assert _as_datetime("") is None
    assert _as_datetime(dt.date(2026, 9, 1)) == dt.datetime(2026, 9, 1, tzinfo=dt.UTC)
    assert _as_datetime("2026-09-01T08:30:00") == dt.datetime(2026, 9, 1, 8, 30, tzinfo=dt.UTC)
    with pytest.raises(WorkbookError, match="date/time"):
        _as_datetime("last tuesday")


# --- ADR-0013: Title / Company / URL are now editable ----------------------


def test_blank_canonical_cells_mean_leave_as_is() -> None:
    data = write_workbook([_row()])
    ws = load_workbook(io.BytesIO(data))
    for col in ("A", "B", "C"):  # Title, Company, URL
        ws["Applications"][f"{col}2"] = None
    buf = io.BytesIO()
    ws.save(buf)

    values = read_workbook(buf.getvalue())[0].values
    assert values["title"] is None
    assert values["company_name"] is None
    assert values["url"] is None


def test_an_invalid_url_cell_is_a_parse_error_not_an_exception() -> None:
    data = write_workbook([_row()])
    ws = load_workbook(io.BytesIO(data))
    ws["Applications"]["C2"] = "definitely not a url"  # the URL column
    buf = io.BytesIO()
    ws.save(buf)

    parsed = read_workbook(buf.getvalue())
    assert parsed[0].parse_error is not None
    assert "URL" in parsed[0].parse_error


def test_as_url_variants() -> None:
    assert _as_url(None) is None
    assert _as_url("") is None
    assert _as_url("https://boards.greenhouse.io/acme/1") == "https://boards.greenhouse.io/acme/1"
    assert _as_url("http://example.com") == "http://example.com"
    with pytest.raises(WorkbookError, match="valid http"):
        _as_url("not a url")
    with pytest.raises(WorkbookError, match="valid http"):
        _as_url("ftp://example.com/file")
