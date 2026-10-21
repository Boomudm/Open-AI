"""Cache index + chat message confidence persistence

Revision ID: 0027_cache_confidence
Revises: 0026_chat_attachments
Create Date: 2026-06-18
"""
from __future__ import annotations

import hashlib
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0027_cache_confidence"
down_revision: Union[str, None] = "0026_chat_attachments"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _q_hash(text: str) -> str:
    normalized = " ".join((text or "").strip().lower().split())
    return hashlib.sha256(normalized.encode()).hexdigest()


def upgrade() -> None:
    op.add_column(
        "verified_qa_cache",
        sa.Column("question_hash", sa.String(64), nullable=True),
    )
    op.add_column(
        "verified_qa_cache",
        sa.Column("filter_fingerprint", sa.String(64), nullable=True),
    )
    conn = op.get_bind()
    rows = conn.execute(
        sa.text("SELECT cache_id, question_text FROM verified_qa_cache")
    ).fetchall()
    for cache_id, question_text in rows:
        conn.execute(
            sa.text(
                "UPDATE verified_qa_cache SET question_hash = :qh WHERE cache_id = :cid"
            ),
            {"qh": _q_hash(question_text or ""), "cid": cache_id},
        )
    op.alter_column("verified_qa_cache", "question_hash", nullable=False)
    op.create_index(
        "ix_verified_qa_cache_lookup",
        "verified_qa_cache",
        ["factory_id", "question_hash", "verification_method"],
    )

    op.add_column(
        "chat_messages",
        sa.Column("confidence_tier", sa.String(10), nullable=True),
    )
    op.add_column(
        "chat_messages",
        sa.Column("cache_hit", sa.Boolean(), nullable=False, server_default="false"),
    )


def downgrade() -> None:
    op.drop_column("chat_messages", "cache_hit")
    op.drop_column("chat_messages", "confidence_tier")
    op.drop_index("ix_verified_qa_cache_lookup", table_name="verified_qa_cache")
    op.drop_column("verified_qa_cache", "filter_fingerprint")
    op.drop_column("verified_qa_cache", "question_hash")
