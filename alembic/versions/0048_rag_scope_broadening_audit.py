"""rag_scope_broadening_audit — Phase 10 fallback ladder audit."""

from __future__ import annotations

from alembic import op

revision = "0048_rag_scope_broadening_audit"
down_revision = "0047_ingest_saga_consistency"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS rag_scope_broadening_audit (
            audit_id uuid PRIMARY KEY,
            user_id uuid NULL,
            factory_id varchar(20) NULL,
            question text NOT NULL,
            fallback_level integer NOT NULL,
            original_filter jsonb NULL,
            broadened_filter jsonb NULL,
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_rag_scope_broadening_audit_factory_id
        ON rag_scope_broadening_audit (factory_id)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_rag_scope_broadening_audit_factory_id")
    op.execute("DROP TABLE IF EXISTS rag_scope_broadening_audit")
