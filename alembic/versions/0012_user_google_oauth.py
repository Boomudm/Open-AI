"""Add Google OAuth fields to users (google_id, picture_url)

Revision ID: 0012_user_google_oauth
Revises: 0011_reorder_requests
Create Date: 2026-06-11
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0012_user_google_oauth"
down_revision: Union[str, None] = "0011_reorder_requests"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("google_id", sa.String(255), nullable=True))
    op.add_column("users", sa.Column("picture_url", sa.String(512), nullable=True))
    op.create_index("ix_users_google_id", "users", ["google_id"], unique=True)
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ix_users_email_unique_lower
        ON users (lower(email))
        WHERE email IS NOT NULL AND btrim(email) <> ''
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_users_email_unique_lower")
    op.drop_index("ix_users_google_id", table_name="users")
    op.drop_column("users", "picture_url")
    op.drop_column("users", "google_id")
