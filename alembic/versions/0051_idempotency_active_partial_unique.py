"""Phase 2 — partial unique idempotency index for active jobs only."""

from __future__ import annotations

from alembic import op

revision = "0051_idempotency_partial_uq"
down_revision = "0050_audit_events_immutable"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_ingestion_jobs_idempotency_key")
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_ingestion_jobs_idempotency_active
        ON ingestion_jobs (idempotency_key)
        WHERE idempotency_key IS NOT NULL
          AND status IN ('queued', 'running', 'retrying')
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_ingestion_jobs_idempotency_active")
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_ingestion_jobs_idempotency_key
        ON ingestion_jobs (idempotency_key)
        WHERE idempotency_key IS NOT NULL
        """
    )
