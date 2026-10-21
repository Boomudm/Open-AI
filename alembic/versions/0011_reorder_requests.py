"""reorder_requests table for spare-part reorder workflow

Revision ID: 0011_reorder_requests
Revises: 0010_ingest_job_filename
Create Date: 2026-05-29
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011_reorder_requests"
down_revision: Union[str, None] = "0010_ingest_job_filename"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "reorder_requests",
        sa.Column(
            "request_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuid_generate_v4()"),
        ),
        sa.Column(
            "part_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("spare_parts.part_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("qty", sa.Integer, nullable=False),
        sa.Column("manufacturer", sa.String(100)),
        sa.Column("lead_time_days", sa.Integer),
        sa.Column("status", sa.String(20), server_default="pending", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("created_by", sa.String(100)),
    )
    op.create_index("ix_reorder_requests_part", "reorder_requests", ["part_id"])
    op.create_index("ix_reorder_requests_status", "reorder_requests", ["status"])


def downgrade() -> None:
    op.drop_index("ix_reorder_requests_status", table_name="reorder_requests")
    op.drop_index("ix_reorder_requests_part", table_name="reorder_requests")
    op.drop_table("reorder_requests")
