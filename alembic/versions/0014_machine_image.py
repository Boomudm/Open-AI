"""Machine cover image — image_storage_uri, image_updated_at

Revision ID: 0014_machine_image
Revises: 0013_document_mvp
Create Date: 2026-06-11
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0014_machine_image"
down_revision: Union[str, None] = "0013_document_mvp"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("machines", sa.Column("image_storage_uri", sa.Text(), nullable=True))
    op.add_column(
        "machines",
        sa.Column("image_updated_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("machines", "image_updated_at")
    op.drop_column("machines", "image_storage_uri")
