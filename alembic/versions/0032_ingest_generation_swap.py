"""Atomic ingest swap: active_ingest_generation on documents, ingest_generation on chunks.

Revision ID: 0032_ingest_generation
Revises: 0031_sql_readonly_rls
Create Date: 2026-06-19
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0032_ingest_generation"
down_revision: Union[str, None] = "0031_sql_readonly_rls"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("active_ingest_generation", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "document_chunks",
        sa.Column("ingest_generation", sa.Integer(), nullable=False, server_default="1"),
    )
    op.create_index(
        "ix_document_chunks_doc_generation",
        "document_chunks",
        ["doc_id", "ingest_generation"],
    )


def downgrade() -> None:
    op.drop_index("ix_document_chunks_doc_generation", table_name="document_chunks")
    op.drop_column("document_chunks", "ingest_generation")
    op.drop_column("documents", "active_ingest_generation")
