"""Insights Phase 2 — topic tag provenance + nullable alert machine_id

Revision ID: 0019_insights_phase2
Revises: 0018_chat_session_pin
Create Date: 2026-06-11
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0019_insights_phase2"
down_revision: Union[str, None] = "0018_chat_session_pin"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "question_analytics",
        sa.Column("topic_source", sa.String(20), nullable=True),
    )
    op.add_column(
        "question_analytics",
        sa.Column("tagged_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.alter_column("alert_records", "machine_id", existing_type=sa.String(20), nullable=True)


def downgrade() -> None:
    op.alter_column("alert_records", "machine_id", existing_type=sa.String(20), nullable=False)
    op.drop_column("question_analytics", "tagged_at")
    op.drop_column("question_analytics", "topic_source")
