"""Verified Q&A cache for similar-question reuse

Revision ID: 0020_verified_qa_cache
Revises: 0019_insights_phase2
Create Date: 2026-06-11
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID

revision: str = "0020_verified_qa_cache"
down_revision: Union[str, None] = "0019_insights_phase2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "verified_qa_cache",
        sa.Column("cache_id", UUID(as_uuid=True), primary_key=True),
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
        sa.Column("intent", sa.String(20), nullable=False),
        sa.Column("question_text", sa.Text(), nullable=False),
        sa.Column("question_embedding", JSONB(), nullable=True),
        sa.Column("answer_text", sa.Text(), nullable=False),
        sa.Column("sources", JSONB(), nullable=True),
        sa.Column(
            "source_doc_ids",
            ARRAY(UUID(as_uuid=True)),
            nullable=False,
            server_default=sa.text("'{}'::uuid[]"),
        ),
        sa.Column("verification_method", sa.String(40), nullable=True),
        sa.Column("verification_score", sa.Float(), nullable=True),
        sa.Column(
            "source_message_id",
            UUID(as_uuid=True),
            sa.ForeignKey("chat_messages.message_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("hit_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_verified_qa_cache_factory_intent",
        "verified_qa_cache",
        ["factory_id", "intent"],
    )
    op.create_index(
        "ix_verified_qa_cache_factory_machine",
        "verified_qa_cache",
        ["factory_id", "machine_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_verified_qa_cache_factory_machine", table_name="verified_qa_cache")
    op.drop_index("ix_verified_qa_cache_factory_intent", table_name="verified_qa_cache")
    op.drop_table("verified_qa_cache")
