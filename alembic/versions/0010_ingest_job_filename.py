"""Add upload metadata columns to ingestion_jobs.

Revision ID: 0010_ingest_job_filename
Revises: 0009_drop_telemetry_advisory
Create Date: 2026-05-29
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0010_ingest_job_filename"
down_revision: Union[str, None] = "0009_drop_telemetry_advisory"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "ingestion_jobs",
        sa.Column("original_filename", sa.String(500), nullable=True),
    )
    op.add_column(
        "ingestion_jobs",
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "ingestion_jobs",
        sa.Column("factory_id", sa.String(20), nullable=True),
    )
    op.add_column(
        "ingestion_jobs",
        sa.Column("machine_id", sa.String(20), nullable=True),
    )
    op.execute(
        """
        UPDATE ingestion_jobs j
        SET original_filename = d.source_file,
            file_size_bytes = d.file_size_bytes,
            factory_id = d.factory_id,
            machine_id = d.machine_id
        FROM documents d
        WHERE j.doc_id = d.doc_id
          AND j.original_filename IS NULL
        """
    )


def downgrade() -> None:
    op.drop_column("ingestion_jobs", "machine_id")
    op.drop_column("ingestion_jobs", "factory_id")
    op.drop_column("ingestion_jobs", "file_size_bytes")
    op.drop_column("ingestion_jobs", "original_filename")
