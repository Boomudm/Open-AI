"""Document library MVP — mime_type, original_filename, access log

Revision ID: 0013_document_mvp
Revises: 0012_user_google_oauth
Create Date: 2026-06-11
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0013_document_mvp"
down_revision: Union[str, None] = "0012_user_google_oauth"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("mime_type", sa.String(127), nullable=True))
    op.add_column("documents", sa.Column("original_filename", sa.String(500), nullable=True))
    op.execute(
        """
        UPDATE documents
        SET original_filename = source_file
        WHERE original_filename IS NULL AND source_file IS NOT NULL
        """
    )
    op.create_table(
        "document_access_log",
        sa.Column("log_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("doc_id", UUID(as_uuid=True), sa.ForeignKey("documents.doc_id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True),
        sa.Column("action", sa.String(20), nullable=False),
        sa.Column("ip", sa.String(45), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_document_access_log_doc_id", "document_access_log", ["doc_id"])
    op.create_index("ix_document_access_log_user_id", "document_access_log", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_document_access_log_user_id", table_name="document_access_log")
    op.drop_index("ix_document_access_log_doc_id", table_name="document_access_log")
    op.drop_table("document_access_log")
    op.drop_column("documents", "original_filename")
    op.drop_column("documents", "mime_type")
