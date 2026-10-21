"""Chat message attachments for /chat file context

Revision ID: 0026_chat_attachments
Revises: 0025_chunk_search_mirror
Create Date: 2026-06-16
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0026_chat_attachments"
down_revision: Union[str, None] = "0025_chunk_search_mirror"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "chat_message_attachments",
        sa.Column("attachment_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "message_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("chat_messages.message_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("chat_sessions.session_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("storage_uri", sa.Text(), nullable=False),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("mime_type", sa.String(127), nullable=False),
        sa.Column("file_size_bytes", sa.Integer(), nullable=False),
        sa.Column("extracted_text", sa.Text(), nullable=True),
        sa.Column("extract_status", sa.String(32), nullable=True),
        sa.Column("extract_error", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index(
        "ix_chat_message_attachments_message_id",
        "chat_message_attachments",
        ["message_id"],
    )
    op.create_index(
        "ix_chat_message_attachments_session_id",
        "chat_message_attachments",
        ["session_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_chat_message_attachments_session_id", table_name="chat_message_attachments")
    op.drop_index("ix_chat_message_attachments_message_id", table_name="chat_message_attachments")
    op.drop_table("chat_message_attachments")
