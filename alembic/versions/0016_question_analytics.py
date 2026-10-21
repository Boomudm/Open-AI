"""Question analytics — AI question snapshots for insights dashboard

Revision ID: 0016_question_analytics
Revises: 0015_knowledge_feedback
Create Date: 2026-06-11
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0016_question_analytics"
down_revision: Union[str, None] = "0015_knowledge_feedback"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "question_analytics",
        sa.Column("analytics_id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "message_id",
            UUID(as_uuid=True),
            sa.ForeignKey("chat_messages.message_id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "factory_id",
            sa.String(20),
            sa.ForeignKey("factories.factory_id"),
            nullable=True,
        ),
        sa.Column(
            "machine_id",
            sa.String(20),
            sa.ForeignKey("machines.machine_id"),
            nullable=True,
        ),
        sa.Column("intent", sa.String(20), nullable=False),
        sa.Column("topic_label", sa.String(100), nullable=True),
        sa.Column("topic_confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("asked_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_question_analytics_factory_asked", "question_analytics", ["factory_id", "asked_at"])
    op.create_index("ix_question_analytics_topic", "question_analytics", ["factory_id", "topic_label"])
    op.create_index("ix_question_analytics_machine_asked", "question_analytics", ["machine_id", "asked_at"])


def downgrade() -> None:
    op.drop_index("ix_question_analytics_machine_asked", table_name="question_analytics")
    op.drop_index("ix_question_analytics_topic", table_name="question_analytics")
    op.drop_index("ix_question_analytics_factory_asked", table_name="question_analytics")
    op.drop_table("question_analytics")
