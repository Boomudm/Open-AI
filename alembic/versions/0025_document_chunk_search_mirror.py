"""Add searchable chunk text mirror

Revision ID: 0025_chunk_search_mirror
Revises: 0024_repair_history_doc_idx
Create Date: 2026-06-12
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0025_chunk_search_mirror"
down_revision: Union[str, None] = "0024_repair_history_doc_idx"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("document_chunks", sa.Column("content", sa.Text(), nullable=True))
    op.add_column("document_chunks", sa.Column("payload", postgresql.JSONB(), nullable=True))
    op.create_index(
        "ix_document_chunks_doc_chunk",
        "document_chunks",
        ["doc_id", "chunk_index"],
    )
    op.execute(
        """
        CREATE INDEX ix_document_chunks_content_trgm
        ON document_chunks USING gin (content gin_trgm_ops)
        WHERE content IS NOT NULL
        """
    )
    op.execute(
        """
        CREATE INDEX ix_document_chunks_content_tsv
        ON document_chunks USING gin (to_tsvector('simple', coalesce(content, '')))
        WHERE content IS NOT NULL
        """
    )
    op.execute(
        """
        CREATE INDEX ix_document_chunks_payload_gin
        ON document_chunks USING gin (payload)
        WHERE payload IS NOT NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_document_chunks_payload_gin")
    op.execute("DROP INDEX IF EXISTS ix_document_chunks_content_tsv")
    op.execute("DROP INDEX IF EXISTS ix_document_chunks_content_trgm")
    op.drop_index("ix_document_chunks_doc_chunk", table_name="document_chunks")
    op.drop_column("document_chunks", "payload")
    op.drop_column("document_chunks", "content")
