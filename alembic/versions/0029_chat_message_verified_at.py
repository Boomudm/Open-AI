"""Add verified_at to chat_messages for admin verify persistence

Revision ID: 0029_verified_at
Revises: 0028_factory_audit
Create Date: 2026-06-18
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0029_verified_at"
down_revision: Union[str, None] = "0028_factory_audit"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "chat_messages",
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("chat_messages", "verified_at")
