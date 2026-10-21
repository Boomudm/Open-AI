"""Phase 3 — ingestion event log and OCR skip counter.

Revision ID: 0043_ingest_pipeline_events
Revises: 0042_ingest_trust_boundary
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0043_ingest_pipeline_events"
down_revision = "0042_ingest_trust_boundary"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ingestion_events",
        sa.Column("event_id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "job_id",
            UUID(as_uuid=True),
            sa.ForeignKey("ingestion_jobs.job_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("ts", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("stage", sa.String(length=32), nullable=False),
        sa.Column("level", sa.String(length=16), nullable=False, server_default="info"),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("detail_json", JSONB, nullable=True),
    )
    op.create_index("ix_ingestion_events_job_id", "ingestion_events", ["job_id"])
    op.create_index("ix_ingestion_events_ts", "ingestion_events", ["ts"])
    op.add_column(
        "ingestion_jobs",
        sa.Column("rows_skipped_ocr", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )


def downgrade() -> None:
    op.drop_column("ingestion_jobs", "rows_skipped_ocr")
    op.drop_index("ix_ingestion_events_ts", table_name="ingestion_events")
    op.drop_index("ix_ingestion_events_job_id", table_name="ingestion_events")
    op.drop_table("ingestion_events")
