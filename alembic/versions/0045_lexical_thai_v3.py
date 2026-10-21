"""Phase 6 — Thai lexical columns and industrial boost tokens.

Revision ID: 0045_lexical_thai_v3
Revises: 0044_chunk_schema_v2
"""

from __future__ import annotations

from alembic import op

revision = "0045_lexical_thai_v3"
down_revision = "0044_chunk_schema_v2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE document_chunks
        ADD COLUMN IF NOT EXISTS content_th_tokenized text,
        ADD COLUMN IF NOT EXISTS boost_tokens text[]
        """
    )
    op.execute(
        """
        ALTER TABLE document_chunks
        ADD COLUMN IF NOT EXISTS content_tsv_th tsvector
        GENERATED ALWAYS AS (
            to_tsvector('simple', coalesce(content_th_tokenized, ''))
        ) STORED
        """
    )
    op.execute("DROP INDEX IF EXISTS ix_document_chunks_content_tsv_th")
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_document_chunks_content_tsv_th
        ON document_chunks USING gin (content_tsv_th)
        WHERE content_th_tokenized IS NOT NULL
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_document_chunks_boost_tokens
        ON document_chunks USING gin (boost_tokens)
        WHERE boost_tokens IS NOT NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_document_chunks_boost_tokens")
    op.execute("DROP INDEX IF EXISTS ix_document_chunks_content_tsv_th")
    op.execute("ALTER TABLE document_chunks DROP COLUMN IF EXISTS content_tsv_th")
    op.execute("ALTER TABLE document_chunks DROP COLUMN IF EXISTS boost_tokens")
    op.execute("ALTER TABLE document_chunks DROP COLUMN IF EXISTS content_th_tokenized")
