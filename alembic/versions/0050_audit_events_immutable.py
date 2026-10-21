"""audit_events_immutable — hash-chained WORM audit (Phase 14)."""

from __future__ import annotations

from alembic import op

revision = "0050_audit_events_immutable"
down_revision = "0049_qa_cache_fingerprint_v2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS audit_events_immutable (
            event_id uuid PRIMARY KEY,
            event_type varchar(64) NOT NULL,
            occurred_at timestamptz NOT NULL,
            actor_id varchar(64) NULL,
            factory_id varchar(20) NULL,
            payload jsonb NOT NULL DEFAULT '{}',
            prev_hash varchar(64) NULL,
            event_hash varchar(64) NOT NULL UNIQUE
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_audit_events_immutable_occurred_at
        ON audit_events_immutable (occurred_at)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_audit_events_immutable_factory_id
        ON audit_events_immutable (factory_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_audit_events_immutable_event_type
        ON audit_events_immutable (event_type)
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION deny_audit_events_immutable_mutation()
        RETURNS trigger AS $$
        BEGIN
          RAISE EXCEPTION 'audit_events_immutable is append-only';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute("DROP TRIGGER IF EXISTS audit_events_immutable_no_update ON audit_events_immutable")
    op.execute(
        """
        CREATE TRIGGER audit_events_immutable_no_update
        BEFORE UPDATE OR DELETE ON audit_events_immutable
        FOR EACH ROW EXECUTE FUNCTION deny_audit_events_immutable_mutation()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS audit_events_immutable_no_update ON audit_events_immutable")
    op.execute("DROP FUNCTION IF EXISTS deny_audit_events_immutable_mutation()")
    op.execute("DROP INDEX IF EXISTS ix_audit_events_immutable_event_type")
    op.execute("DROP INDEX IF EXISTS ix_audit_events_immutable_factory_id")
    op.execute("DROP INDEX IF EXISTS ix_audit_events_immutable_occurred_at")
    op.execute("DROP TABLE IF EXISTS audit_events_immutable")
