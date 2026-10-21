"""Add sensitivity_level column to documents table.

Revision ID: 0052
Revises: 0051
Create Date: 2026-06-25
"""

from alembic import op
import sqlalchemy as sa

revision = "0052_document_sensitivity_level"
down_revision = "0051_idempotency_partial_uq"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("sensitivity_level", sa.String(20), nullable=True),
    )
    op.create_index(
        "ix_documents_sensitivity_level",
        "documents",
        ["sensitivity_level"],
    )


def downgrade() -> None:
    op.drop_index("ix_documents_sensitivity_level", table_name="documents")
    op.drop_column("documents", "sensitivity_level")
