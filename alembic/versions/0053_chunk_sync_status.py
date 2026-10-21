"""Add sync_status column to document_chunks for outbox pattern tracking.

Revision ID: 0053
Revises: 0052_document_sensitivity_level
Create Date: 2026-06-29
"""

from alembic import op
import sqlalchemy as sa

revision = "0053_chunk_sync_status"
down_revision = "0052_document_sensitivity_level"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = {col["name"] for col in inspector.get_columns("document_chunks")}
    if "sync_status" not in existing_columns:
        op.add_column(
            "document_chunks",
            sa.Column(
                "sync_status",
                sa.String(20),
                nullable=False,
                server_default="synced",
            ),
        )
    existing_indexes = {idx["name"] for idx in inspector.get_indexes("document_chunks")}
    if "ix_document_chunks_sync_status" not in existing_indexes:
        op.create_index(
            "ix_document_chunks_sync_status",
            "document_chunks",
            ["sync_status"],
        )


def downgrade() -> None:
    op.drop_index("ix_document_chunks_sync_status", table_name="document_chunks")
    op.drop_column("document_chunks", "sync_status")
