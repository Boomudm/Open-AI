"""External Postgres data sources for live Text-to-SQL (admin-configured).

Revision ID: 0054_external_data_sources
Revises: 0053_chunk_sync_status
Create Date: 2026-07-01
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0054_external_data_sources"
down_revision = "0053_chunk_sync_status"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "external_data_sources",
        sa.Column("source_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "factory_id",
            sa.String(20),
            sa.ForeignKey("factories.factory_id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("host", sa.String(255), nullable=False),
        sa.Column("port", sa.Integer(), nullable=False, server_default="5432"),
        sa.Column("database_name", sa.String(128), nullable=False),
        sa.Column("username", sa.String(128), nullable=False),
        sa.Column("password_encrypted", sa.Text(), nullable=False),
        sa.Column("ssl_mode", sa.String(32), nullable=False, server_default="prefer"),
        sa.Column("scope_column", sa.String(128), nullable=True),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.user_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_external_data_sources_factory_id",
        "external_data_sources",
        ["factory_id"],
    )
    op.create_index(
        "ix_external_data_sources_enabled",
        "external_data_sources",
        ["is_enabled"],
    )

    op.create_table(
        "external_data_source_tables",
        sa.Column("table_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "source_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("external_data_sources.source_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("schema_name", sa.String(128), nullable=False, server_default="public"),
        sa.Column("table_name", sa.String(128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "columns_meta",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.UniqueConstraint(
            "source_id",
            "schema_name",
            "table_name",
            name="uq_external_data_source_tables_source_schema_table",
        ),
    )
    op.create_index(
        "ix_external_data_source_tables_source_id",
        "external_data_source_tables",
        ["source_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_external_data_source_tables_source_id", table_name="external_data_source_tables")
    op.drop_table("external_data_source_tables")
    op.drop_index("ix_external_data_sources_enabled", table_name="external_data_sources")
    op.drop_index("ix_external_data_sources_factory_id", table_name="external_data_sources")
    op.drop_table("external_data_sources")
