"""Per-table factory/job-position access scoping for external data sources.

Revision ID: 0056_external_table_scope
Revises: 0055_ingest_job_doc_setnull
Create Date: 2026-07-02

A single external Postgres connection (e.g. a shared ERP/MES database) can
hold tables meant for different audiences — some factory-specific, some
role-specific (HR, finance). Previously access was only scoped at the
connection level (one factory_id or "all factories"). This adds two
many-to-many join tables so each allowed table can independently restrict
which factories and/or which job positions may see it in chat.

Empty on both sides = no extra restriction beyond the connection's own scope.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0056_external_table_scope"
down_revision = "0055_ingest_job_doc_setnull"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "external_table_factories",
        sa.Column(
            "table_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("external_data_source_tables.table_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "factory_id",
            sa.String(20),
            sa.ForeignKey("factories.factory_id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )
    op.create_table(
        "external_table_job_positions",
        sa.Column(
            "table_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("external_data_source_tables.table_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "position_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("job_positions.position_id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )


def downgrade() -> None:
    op.drop_table("external_table_job_positions")
    op.drop_table("external_table_factories")
