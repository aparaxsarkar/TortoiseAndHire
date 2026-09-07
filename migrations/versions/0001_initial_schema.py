"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-09-07

Full schema: companies, sources, jobs, source_postings, filtered_postings,
applications, ingestion_runs, ingestion_errors, application_import_runs.

Constraint highlights (see ADR-0002, ADR-0003, ADR-0009, ADR-0011):
  - source_postings / filtered_postings: UNIQUE (source_id, dedup_key)
  - source_postings: partial UNIQUE (source_id, source_job_id) WHERE source_job_id IS NOT NULL
  - applications.job_id -> jobs: FK ON DELETE RESTRICT (never CASCADE), and job_id is UNIQUE (1:1)
  - ingestion_errors.run_id -> ingestion_runs: FK ON DELETE CASCADE (the one intentional cascade)
  - every other FK: ON DELETE RESTRICT
  - no triggers anywhere
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NOW = sa.text("now()")


def upgrade() -> None:
    op.create_table(
        "application_import_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("filename", sa.Text(), nullable=False),
        sa.Column("uploaded_at", sa.TIMESTAMP(timezone=True), server_default=_NOW, nullable=False),
        sa.Column("committed", sa.Boolean(), server_default="false", nullable=False),
        sa.Column(
            "stats",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column(
            "report",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=_NOW, nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_application_import_runs")),
    )
    op.create_table(
        "companies",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("normalized_name", sa.Text(), nullable=False),
        sa.Column("domain", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=_NOW, nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=_NOW, nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_companies")),
        sa.UniqueConstraint("normalized_name", name="uq_companies_normalized_name"),
    )
    op.create_table(
        "sources",
        sa.Column("id", sa.SmallInteger(), autoincrement=True, nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=_NOW, nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sources")),
        sa.UniqueConstraint("slug", name="uq_sources_slug"),
    )
    op.create_table(
        "filtered_postings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.SmallInteger(), nullable=False),
        sa.Column("source_job_id", sa.Text(), nullable=True),
        sa.Column("canonical_url", sa.Text(), nullable=False),
        sa.Column("dedup_key", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("company_name", sa.Text(), nullable=True),
        sa.Column("reasons", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("ruleset_version", sa.Text(), nullable=False),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("first_seen_at", sa.TIMESTAMP(timezone=True), server_default=_NOW, nullable=False),
        sa.Column("last_seen_at", sa.TIMESTAMP(timezone=True), server_default=_NOW, nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=_NOW, nullable=False),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["sources.id"],
            name=op.f("fk_filtered_postings_source_id_sources"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_filtered_postings")),
        sa.UniqueConstraint(
            "source_id", "dedup_key", name="uq_filtered_postings_source_id_dedup_key"
        ),
    )
    op.create_table(
        "ingestion_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.SmallInteger(), nullable=False),
        sa.Column("trigger", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), server_default=_NOW, nullable=False),
        sa.Column("finished_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "stats",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=_NOW, nullable=False),
        sa.CheckConstraint(
            "status IN ('running', 'success', 'partial', 'failed', 'skipped')",
            name=op.f("ck_ingestion_runs_run_status"),
        ),
        sa.CheckConstraint(
            "trigger IN ('manual_api', 'cli', 'scheduled')",
            name=op.f("ck_ingestion_runs_run_trigger"),
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["sources.id"],
            name=op.f("fk_ingestion_runs_source_id_sources"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ingestion_runs")),
    )
    op.create_index(
        "ix_ingestion_runs_source_id_started_at",
        "ingestion_runs",
        ["source_id", "started_at"],
        unique=False,
    )
    op.create_table(
        "jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("normalized_title", sa.Text(), nullable=False),
        sa.Column("location_raw", sa.Text(), nullable=True),
        sa.Column("location_city", sa.Text(), nullable=True),
        sa.Column("location_region", sa.Text(), nullable=True),
        sa.Column("location_country", sa.Text(), nullable=True),
        sa.Column("remote", sa.Boolean(), nullable=True),
        sa.Column("employment_type", sa.Text(), nullable=True),
        sa.Column("department", sa.Text(), nullable=True),
        sa.Column("description_text", sa.Text(), nullable=True),
        sa.Column("description_html", sa.Text(), nullable=True),
        sa.Column("posted_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("first_seen_at", sa.TIMESTAMP(timezone=True), server_default=_NOW, nullable=False),
        sa.Column("last_seen_at", sa.TIMESTAMP(timezone=True), server_default=_NOW, nullable=False),
        sa.Column("status", sa.Text(), server_default="open", nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=_NOW, nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=_NOW, nullable=False),
        sa.CheckConstraint(
            "status IN ('open', 'closed', 'unknown')", name=op.f("ck_jobs_job_status")
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_jobs_company_id_companies"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_jobs")),
    )
    op.create_index("ix_jobs_company_id", "jobs", ["company_id"], unique=False)
    op.create_index("ix_jobs_normalized_title", "jobs", ["normalized_title"], unique=False)
    op.create_index("ix_jobs_posted_at", "jobs", ["posted_at"], unique=False)
    op.create_table(
        "applications",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("applied", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("applied_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("networking", sa.Text(), server_default="none", nullable=False),
        sa.Column("networking_notes", sa.Text(), nullable=True),
        sa.Column("outcome", sa.Text(), server_default="none", nullable=False),
        sa.Column("application_url", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
        sa.Column("updated_via", sa.Text(), server_default="api", nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=_NOW, nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=_NOW, nullable=False),
        sa.CheckConstraint(
            "networking IN ('none', 'in_progress', 'contact_made', 'referral')",
            name=op.f("ck_applications_networking_status"),
        ),
        sa.CheckConstraint(
            "outcome IN ('none', 'oa', 'screen', 'onsite', 'offer', 'rejected', 'withdrawn', 'ghosted')",
            name=op.f("ck_applications_application_outcome"),
        ),
        sa.CheckConstraint(
            "updated_via IN ('api', 'admin_ui', 'excel_import')",
            name=op.f("ck_applications_updated_via"),
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["jobs.id"],
            name=op.f("fk_applications_job_id_jobs"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_applications")),
        sa.UniqueConstraint("job_id", name="uq_applications_job_id"),
    )
    op.create_table(
        "ingestion_errors",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("stage", sa.Text(), nullable=False),
        sa.Column("source_ref", sa.Text(), nullable=True),
        sa.Column("error_type", sa.Text(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("payload_excerpt", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=_NOW, nullable=False),
        sa.CheckConstraint(
            "stage IN ('fetch', 'parse', 'validate', 'identity', 'relevance', 'persist')",
            name=op.f("ck_ingestion_errors_ingestion_stage"),
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["ingestion_runs.id"],
            name=op.f("fk_ingestion_errors_run_id_ingestion_runs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ingestion_errors")),
    )
    op.create_index("ix_ingestion_errors_run_id", "ingestion_errors", ["run_id"], unique=False)
    op.create_table(
        "source_postings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.SmallInteger(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("source_job_id", sa.Text(), nullable=True),
        sa.Column("canonical_url", sa.Text(), nullable=False),
        sa.Column("dedup_key", sa.Text(), nullable=False),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("content_hash", sa.Text(), nullable=False),
        sa.Column(
            "first_ingested_at", sa.TIMESTAMP(timezone=True), server_default=_NOW, nullable=False
        ),
        sa.Column(
            "last_ingested_at", sa.TIMESTAMP(timezone=True), server_default=_NOW, nullable=False
        ),
        sa.Column("last_run_id", sa.Uuid(), nullable=True),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=_NOW, nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=_NOW, nullable=False),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["jobs.id"],
            name=op.f("fk_source_postings_job_id_jobs"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["last_run_id"],
            ["ingestion_runs.id"],
            name=op.f("fk_source_postings_last_run_id_ingestion_runs"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["sources.id"],
            name=op.f("fk_source_postings_source_id_sources"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_source_postings")),
        sa.UniqueConstraint(
            "source_id", "dedup_key", name="uq_source_postings_source_id_dedup_key"
        ),
    )
    op.create_index(
        "ix_source_postings_canonical_url", "source_postings", ["canonical_url"], unique=False
    )
    op.create_index("ix_source_postings_job_id", "source_postings", ["job_id"], unique=False)
    op.create_index(
        "uq_source_postings_source_job_id_partial",
        "source_postings",
        ["source_id", "source_job_id"],
        unique=True,
        postgresql_where=sa.text("source_job_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_source_postings_source_job_id_partial",
        table_name="source_postings",
        postgresql_where=sa.text("source_job_id IS NOT NULL"),
    )
    op.drop_index("ix_source_postings_job_id", table_name="source_postings")
    op.drop_index("ix_source_postings_canonical_url", table_name="source_postings")
    op.drop_table("source_postings")
    op.drop_index("ix_ingestion_errors_run_id", table_name="ingestion_errors")
    op.drop_table("ingestion_errors")
    op.drop_table("applications")
    op.drop_index("ix_jobs_posted_at", table_name="jobs")
    op.drop_index("ix_jobs_normalized_title", table_name="jobs")
    op.drop_index("ix_jobs_company_id", table_name="jobs")
    op.drop_table("jobs")
    op.drop_index("ix_ingestion_runs_source_id_started_at", table_name="ingestion_runs")
    op.drop_table("ingestion_runs")
    op.drop_table("filtered_postings")
    op.drop_table("sources")
    op.drop_table("companies")
    op.drop_table("application_import_runs")
