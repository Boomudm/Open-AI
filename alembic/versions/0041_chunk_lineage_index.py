"""Phase 11 — chunk lineage columns and parent lookup index.

Revision ID: 0041_chunk_lineage_index
Revises: 0040_multiturn_revision_snapshot
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0041_chunk_lineage_index"
down_revision = "0040_multiturn_revision_snapshot"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "document_chunks",
        sa.Column("content_hash", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "document_chunks",
        sa.Column("embed_model", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "document_chunks",
        sa.Column("embed_model_version", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "ix_document_chunks_doc_parent",
        "document_chunks",
        ["doc_id", "parent_chunk_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_document_chunks_doc_parent", table_name="document_chunks")
    op.drop_column("document_chunks", "embed_model_version")
    op.drop_column("document_chunks", "embed_model")
    op.drop_column("document_chunks", "content_hash")
