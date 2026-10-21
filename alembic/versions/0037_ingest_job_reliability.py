"""Migration: ingest job retry / DLQ columns.

Revision ID: 0037
Revises: 0036
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0037_ingest_job_reliability"
down_revision = "0036_document_quarantine"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ingestion_jobs",
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "ingestion_jobs",
        sa.Column("last_error_code", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "ingestion_jobs",
        sa.Column("dlq_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "ingestion_jobs",
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_ingestion_jobs_dlq_at", "ingestion_jobs", ["dlq_at"])


def downgrade() -> None:
    op.drop_index("ix_ingestion_jobs_dlq_at", table_name="ingestion_jobs")
    op.drop_column("ingestion_jobs", "next_retry_at")
    op.drop_column("ingestion_jobs", "dlq_at")
    op.drop_column("ingestion_jobs", "last_error_code")
    op.drop_column("ingestion_jobs", "attempt_count")
