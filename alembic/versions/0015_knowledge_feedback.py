"""Knowledge feedback — floor feedback loop

Revision ID: 0015_knowledge_feedback
Revises: 0014_machine_image
Create Date: 2026-06-11
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "0015_knowledge_feedback"
down_revision: Union[str, None] = "0014_machine_image"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "knowledge_feedback",
        sa.Column("feedback_id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "factory_id",
            sa.String(20),
            sa.ForeignKey("factories.factory_id"),
            nullable=False,
        ),
        sa.Column(
            "machine_id",
            sa.String(20),
            sa.ForeignKey("machines.machine_id"),
            nullable=True,
        ),
        sa.Column("source_type", sa.String(30), nullable=False),
        sa.Column(
            "doc_id",
            UUID(as_uuid=True),
            sa.ForeignKey("documents.doc_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("page", sa.Integer(), nullable=True),
        sa.Column(
            "session_id",
            UUID(as_uuid=True),
            sa.ForeignKey("chat_sessions.session_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "message_id",
            UUID(as_uuid=True),
            sa.ForeignKey("chat_messages.message_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("comment", sa.Text(), nullable=False),
        sa.Column("issue_type", sa.String(30), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="open"),
        sa.Column("context", JSONB, nullable=True),
        sa.Column("resolution_note", sa.Text(), nullable=True),
        sa.Column(
            "resolved_by",
            UUID(as_uuid=True),
            sa.ForeignKey("users.user_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_by",
            UUID(as_uuid=True),
            sa.ForeignKey("users.user_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_knowledge_feedback_factory_status_created",
        "knowledge_feedback",
        ["factory_id", "status", "created_at"],
    )
    op.create_index("ix_knowledge_feedback_doc_id", "knowledge_feedback", ["doc_id"])
    op.create_index("ix_knowledge_feedback_message_id", "knowledge_feedback", ["message_id"])

    op.create_table(
        "knowledge_feedback_attachments",
        sa.Column("attachment_id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "feedback_id",
            UUID(as_uuid=True),
            sa.ForeignKey("knowledge_feedback.feedback_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("storage_uri", sa.Text(), nullable=False),
        sa.Column("mime_type", sa.String(127), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_knowledge_feedback_attachments_feedback_id",
        "knowledge_feedback_attachments",
        ["feedback_id"],
    )


def downgrade() -> None:
    op.drop_table("knowledge_feedback_attachments")
    op.drop_table("knowledge_feedback")
