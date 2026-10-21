"""Add users.is_super_admin for God Mode access control.

Revision ID: 0035
Revises: 0034
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0035_user_is_super_admin"
down_revision = "0034_crud_performance_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("is_super_admin", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    # Demo admin gets super-admin for local God Mode testing.
    op.execute(
        sa.text(
            "UPDATE users SET is_super_admin = true "
            "WHERE username = 'admin' AND is_super_admin = false"
        )
    )


def downgrade() -> None:
    op.drop_column("users", "is_super_admin")
