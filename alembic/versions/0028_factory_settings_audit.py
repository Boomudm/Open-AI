"""Cache index + chat message confidence persistence

Revision ID: 0028_factory_audit
Revises: 0027_cache_confidence
Create Date: 2026-06-18
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0028_factory_audit"
down_revision: Union[str, None] = "0027_cache_confidence"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "factory_settings",
        sa.Column(
            "factory_id",
            sa.String(20),
            sa.ForeignKey("factories.factory_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("settings", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "audit_retrieval_log",
        sa.Column("log_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("factory_id", sa.String(20), nullable=True, index=True),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("doc_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("page", sa.Integer(), nullable=True),
        sa.Column("route", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_audit_retrieval_log_created", "audit_retrieval_log", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_audit_retrieval_log_created", table_name="audit_retrieval_log")
    op.drop_table("audit_retrieval_log")
    op.drop_table("factory_settings")
