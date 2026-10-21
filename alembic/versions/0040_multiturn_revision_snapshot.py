"""Phase 10 — revision sort keys and chat retrieval audit snapshots.

Revision ID: 0040_multiturn_revision_snapshot
Revises: 0039_chunk_content_tsv
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0040_multiturn_revision_snapshot"
down_revision = "0039_chunk_content_tsv"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("revision_sort_key", sa.Integer(), nullable=True),
    )
    op.create_index(
        "ix_documents_revision_sort_key",
        "documents",
        ["revision_sort_key"],
        unique=False,
    )
    op.add_column(
        "chat_messages",
        sa.Column("retrieval_snapshot", JSONB, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("chat_messages", "retrieval_snapshot")
    op.drop_index("ix_documents_revision_sort_key", table_name="documents")
    op.drop_column("documents", "revision_sort_key")
