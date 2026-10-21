"""Phase 4 — ingest saga state, structured generation, purge outbox.

Revision ID: 0047_ingest_saga_consistency
Revises: 0046_ingest_idempotency_key
"""

from __future__ import annotations

from alembic import op

revision = "0047_ingest_saga_consistency"
down_revision = "0046_ingest_idempotency_key"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE documents
        ADD COLUMN IF NOT EXISTS ingest_saga_state varchar(30)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_documents_ingest_saga_state
        ON documents (ingest_saga_state)
        WHERE ingest_saga_state IS NOT NULL
        """
    )
    op.execute(
        """
        ALTER TABLE repair_history
        ADD COLUMN IF NOT EXISTS ingest_generation integer
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_repair_history_doc_generation
        ON repair_history (doc_id, ingest_generation)
        WHERE doc_id IS NOT NULL
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS ingest_purge_outbox (
            purge_id uuid PRIMARY KEY,
            doc_id uuid NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
            keep_generation integer NOT NULL,
            collection varchar(200),
            status varchar(20) NOT NULL DEFAULT 'pending',
            attempt_count integer NOT NULL DEFAULT 0,
            last_error text,
            next_retry_at timestamptz,
            finished_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_ingest_purge_outbox_status_retry
        ON ingest_purge_outbox (status, next_retry_at)
        WHERE status = 'pending'
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_ingest_purge_outbox_status_retry")
    op.execute("DROP TABLE IF EXISTS ingest_purge_outbox")
    op.execute("DROP INDEX IF EXISTS ix_repair_history_doc_generation")
    op.execute("ALTER TABLE repair_history DROP COLUMN IF EXISTS ingest_generation")
    op.execute("DROP INDEX IF EXISTS ix_documents_ingest_saga_state")
    op.execute("ALTER TABLE documents DROP COLUMN IF EXISTS ingest_saga_state")
