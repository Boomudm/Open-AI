"""Phase 5 — chunk schema version and enforced embed lineage columns.

Revision ID: 0044_chunk_schema_v2
Revises: 0043_ingest_pipeline_events
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0044_chunk_schema_v2"
down_revision = "0043_ingest_pipeline_events"
branch_labels = None
depends_on = None

_DEFAULT_EMBED_VERSION = "2025-06-01"


def upgrade() -> None:
    op.add_column(
        "document_chunks",
        sa.Column(
            "chunk_schema_version",
            sa.Integer(),
            nullable=False,
            server_default="2",
        ),
    )
    op.execute(
        sa.text(
            "UPDATE document_chunks SET embed_model_version = :ver "
            "WHERE embed_model_version IS NULL OR embed_model_version = ''"
        ).bindparams(ver=_DEFAULT_EMBED_VERSION)
    )
    op.execute(
        sa.text(
            "UPDATE document_chunks SET content_hash = LEFT(content_hash, 32) "
            "WHERE content_hash IS NOT NULL AND LENGTH(content_hash) > 32"
        )
    )
    op.execute(
        sa.text(
            "UPDATE document_chunks SET content_hash = MD5(COALESCE(content, '')) "
            "WHERE content_hash IS NULL OR content_hash = ''"
        )
    )
    op.alter_column("document_chunks", "embed_model_version", nullable=False)
    op.alter_column("document_chunks", "content_hash", type_=sa.String(length=32), nullable=False)


def downgrade() -> None:
    op.alter_column("document_chunks", "content_hash", type_=sa.String(length=64), nullable=True)
    op.alter_column("document_chunks", "embed_model_version", nullable=True)
    op.drop_column("document_chunks", "chunk_schema_version")
