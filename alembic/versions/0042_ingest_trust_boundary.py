"""Phase 2 — ingest trust boundary columns and machine_specs.

Revision ID: 0042_ingest_trust_boundary
Revises: 0041_chunk_lineage_index
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0042_ingest_trust_boundary"
down_revision = "0041_chunk_lineage_index"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("policy_findings_json", JSONB, nullable=True))
    op.add_column(
        "documents",
        sa.Column("quarantine_artifact_uri", sa.String(length=1000), nullable=True),
    )

    op.create_table(
        "machine_specs",
        sa.Column("spec_id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column(
            "machine_id",
            sa.String(length=20),
            sa.ForeignKey("machines.machine_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("parameter_name", sa.String(length=64), nullable=False),
        sa.Column("unit", sa.String(length=32), nullable=True),
        sa.Column("min_value", sa.Float(), nullable=True),
        sa.Column("max_value", sa.Float(), nullable=True),
        sa.Column("source", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_machine_specs_machine_id", "machine_specs", ["machine_id"])


def downgrade() -> None:
    op.drop_index("ix_machine_specs_machine_id", table_name="machine_specs")
    op.drop_table("machine_specs")
    op.drop_column("documents", "quarantine_artifact_uri")
    op.drop_column("documents", "policy_findings_json")
