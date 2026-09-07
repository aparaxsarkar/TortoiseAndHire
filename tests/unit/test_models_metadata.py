"""Schema shape checks that need no database - they inspect Base.metadata."""

from __future__ import annotations

from sqlalchemy import CheckConstraint, ForeignKeyConstraint, UniqueConstraint

from app.models import Base

TABLES = {
    "companies",
    "sources",
    "jobs",
    "source_postings",
    "filtered_postings",
    "applications",
    "ingestion_runs",
    "ingestion_errors",
    "application_import_runs",
}


def test_all_tables_registered() -> None:
    assert set(Base.metadata.tables) == TABLES


def test_naming_convention_applied() -> None:
    for table in Base.metadata.tables.values():
        for constraint in table.constraints:
            if constraint.name is not None:
                assert str(constraint.name).startswith(("pk_", "fk_", "uq_", "ck_")), (
                    table.name,
                    constraint.name,
                )
        for index in table.indexes:
            assert str(index.name).startswith(("ix_", "uq_")), (table.name, index.name)


def _fk(table_name: str, column: str) -> ForeignKeyConstraint:
    for fk in Base.metadata.tables[table_name].foreign_key_constraints:
        if column in fk.column_keys:
            return fk
    raise AssertionError(f"no FK on {table_name}.{column}")


def test_applications_job_fk_is_restrict_not_cascade() -> None:
    # ADR-0011: a tracked job can never be deleted out from under a record.
    assert _fk("applications", "job_id").ondelete == "RESTRICT"


def test_ingestion_errors_cascade_from_run() -> None:
    # The one intentional cascade: an error row belongs to its run.
    assert _fk("ingestion_errors", "run_id").ondelete == "CASCADE"


def test_every_other_fk_is_restrict_or_set_null() -> None:
    allowed = {"RESTRICT", "SET NULL"}
    for name in TABLES - {"ingestion_errors"}:
        for fk in Base.metadata.tables[name].foreign_key_constraints:
            assert fk.ondelete in allowed, (name, fk.column_keys, fk.ondelete)


def test_idempotency_anchor_present() -> None:
    # ADR-0002: UNIQUE (source_id, dedup_key) on both ledgers.
    for table_name in ("source_postings", "filtered_postings"):
        uniques = [
            tuple(c.name for c in con.columns)
            for con in Base.metadata.tables[table_name].constraints
            if isinstance(con, UniqueConstraint)
        ]
        assert ("source_id", "dedup_key") in uniques, table_name


def test_partial_unique_on_source_job_id() -> None:
    sp = Base.metadata.tables["source_postings"]
    partial = next(
        (ix for ix in sp.indexes if ix.name == "uq_source_postings_source_job_id_partial"),
        None,
    )
    assert partial is not None
    assert partial.unique is True
    assert partial.dialect_kwargs.get("postgresql_where") is not None


def test_filtered_postings_has_no_fk_to_jobs() -> None:
    # ADR-0009: a filtered posting never becomes a job.
    fp = Base.metadata.tables["filtered_postings"]
    assert "jobs" not in {fk.referred_table.name for fk in fp.foreign_key_constraints}


def test_enum_checks_reference_a_real_column() -> None:
    for table in Base.metadata.tables.values():
        cols = set(table.columns.keys())
        for con in table.constraints:
            if isinstance(con, CheckConstraint) and con.name:
                assert any(col in str(con.sqltext) for col in cols), (table.name, con.name)


def test_expected_indexes_exist() -> None:
    names = {ix.name for table in Base.metadata.tables.values() for ix in table.indexes}
    assert {
        "ix_jobs_company_id",
        "ix_jobs_posted_at",
        "ix_source_postings_job_id",
        "ix_ingestion_runs_source_id_started_at",
        "ix_ingestion_errors_run_id",
    } <= names
