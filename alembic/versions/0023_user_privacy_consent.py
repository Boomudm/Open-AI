"""User privacy policy consent columns

Revision ID: 0023_user_privacy_consent
Revises: 0022_token_version_roles
Create Date: 2026-06-12
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0023_user_privacy_consent"
down_revision: Union[str, None] = "0022_token_version_roles"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("privacy_policy_accepted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("privacy_policy_version", sa.String(20), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "privacy_policy_version")
    op.drop_column("users", "privacy_policy_accepted_at")
