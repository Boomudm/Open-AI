"""Add repair_history doc_id index for re-ingest cleanup

Revision ID: 0024_repair_history_doc_idx
Revises: 0023_user_privacy_consent
Create Date: 2026-06-12
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0024_repair_history_doc_idx"
down_revision: Union[str, None] = "0023_user_privacy_consent"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index("ix_repair_history_doc_id", "repair_history", ["doc_id"])


def downgrade() -> None:
    op.drop_index("ix_repair_history_doc_id", table_name="repair_history")
