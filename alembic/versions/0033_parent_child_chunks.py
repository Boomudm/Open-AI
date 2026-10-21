"""Parent-child chunk linkage for small-to-big retrieval.

Revision ID: 0033_parent_child_chunks
Revises: 0032_ingest_generation
Create Date: 2026-06-19
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0033_parent_child_chunks"
down_revision: Union[str, None] = "0032_ingest_generation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "document_chunks",
        sa.Column("parent_chunk_id", UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "document_chunks",
        sa.Column("chunk_level", sa.String(length=10), nullable=True),
    )
    op.create_index(
        "ix_document_chunks_parent_chunk_id",
        "document_chunks",
        ["parent_chunk_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_document_chunks_parent_chunk_id", table_name="document_chunks")
    op.drop_column("document_chunks", "chunk_level")
    op.drop_column("document_chunks", "parent_chunk_id")
