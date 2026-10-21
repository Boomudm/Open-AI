"""Add parent_content column for PG-only parent-child context (Qdrant payload slimming).

Revision ID: 0038
Revises: 0037
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0038_chunk_parent_content"
down_revision = "0037_ingest_job_reliability"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "document_chunks",
        sa.Column("parent_content", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("document_chunks", "parent_content")
