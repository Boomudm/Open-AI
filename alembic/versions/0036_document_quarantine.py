"""Document quarantine and content policy provenance columns.

Revision ID: 0036
Revises: 0035
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0036_document_quarantine"
down_revision = "0035_user_is_super_admin"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("quarantine_reason", sa.Text(), nullable=True))
    op.add_column("documents", sa.Column("policy_scan_version", sa.String(length=32), nullable=True))
    op.add_column("documents", sa.Column("released_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "documents",
        sa.Column("released_by", sa.UUID(), sa.ForeignKey("users.user_id"), nullable=True),
    )
    op.add_column("documents", sa.Column("content_risk_score", sa.Float(), nullable=True))
    op.add_column(
        "documents",
        sa.Column("retrieval_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.create_index("ix_documents_retrieval_enabled", "documents", ["retrieval_enabled"])


def downgrade() -> None:
    op.drop_index("ix_documents_retrieval_enabled", table_name="documents")
    op.drop_column("documents", "retrieval_enabled")
    op.drop_column("documents", "content_risk_score")
    op.drop_column("documents", "released_by")
    op.drop_column("documents", "released_at")
    op.drop_column("documents", "policy_scan_version")
    op.drop_column("documents", "quarantine_reason")
