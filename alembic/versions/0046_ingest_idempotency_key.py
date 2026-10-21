"""Phase 2 — ingestion job idempotency key.

Revision ID: 0046_ingest_idempotency_key
Revises: 0045_lexical_thai_v3
"""

from __future__ import annotations

from alembic import op

revision = "0046_ingest_idempotency_key"
down_revision = "0045_lexical_thai_v3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE ingestion_jobs
        ADD COLUMN IF NOT EXISTS idempotency_key varchar(200)
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_ingestion_jobs_idempotency_key
        ON ingestion_jobs (idempotency_key)
        WHERE idempotency_key IS NOT NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_ingestion_jobs_idempotency_key")
    op.execute("ALTER TABLE ingestion_jobs DROP COLUMN IF EXISTS idempotency_key")
