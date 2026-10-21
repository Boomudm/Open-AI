"""Stored tsvector column for index-friendly Postgres FTS v2 lexical search.

Revision ID: 0039_chunk_content_tsv
Revises: 0038_chunk_parent_content

Thai/technical recall uses ``simple`` tsvector plus existing pg_trgm GIN on
``content`` (see 0025). A materialized ``content_tsv`` avoids per-row
``to_tsvector()`` in hot queries and enables a dedicated GIN index.
"""

from __future__ import annotations

from alembic import op

revision = "0039_chunk_content_tsv"
down_revision = "0038_chunk_parent_content"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE document_chunks
        ADD COLUMN IF NOT EXISTS content_tsv tsvector
        GENERATED ALWAYS AS (to_tsvector('simple', coalesce(content, ''))) STORED
        """
    )
    op.execute("DROP INDEX IF EXISTS ix_document_chunks_content_tsv")
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_document_chunks_content_tsv_col
        ON document_chunks USING gin (content_tsv)
        WHERE content IS NOT NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_document_chunks_content_tsv_col")
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_document_chunks_content_tsv
        ON document_chunks USING gin (to_tsvector('simple', coalesce(content, '')))
        WHERE content IS NOT NULL
        """
    )
    op.execute("ALTER TABLE document_chunks DROP COLUMN IF EXISTS content_tsv")
