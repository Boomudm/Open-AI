"""Optional shadow_routing_log table — applied only when shadow/agentic routing is enabled.

Revision ID: 0030_shadow_routing_log
Revises: 0029_verified_at
Create Date: 2026-06-19

Set ROUTING_MODE=shadow or ROUTING_MODE=agentic before running upgrade to create
the table. Default `alembic upgrade head` with ROUTING_MODE=legacy is a no-op for
this revision so production DBs stay unchanged until shadow mode is intentional.
"""
from __future__ import annotations

import os
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "0030_shadow_routing_log"
down_revision: Union[str, None] = "0029_verified_at"
branch_labels: Union[str, Sequence[str], None] = ("shadow_routing",)
depends_on: Union[str, Sequence[str], None] = None


def _routing_mode_enabled() -> bool:
    mode = os.environ.get("ROUTING_MODE", "legacy").strip().lower()
    return mode in ("shadow", "agentic")


def upgrade() -> None:
    if not _routing_mode_enabled():
        return
    op.create_table(
        "shadow_routing_log",
        sa.Column("shadow_log_id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "message_id",
            UUID(as_uuid=True),
            sa.ForeignKey("chat_messages.message_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "session_id",
            UUID(as_uuid=True),
            sa.ForeignKey("chat_sessions.session_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "asked_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("routing_mode", sa.String(20), nullable=False, server_default="shadow"),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("effective_question", sa.Text(), nullable=True),
        sa.Column("factory_id", sa.String(20), nullable=True),
        sa.Column("machine_id", sa.String(20), nullable=True),
        sa.Column("document_type", sa.String(64), nullable=True),
        sa.Column("filter_fingerprint", sa.String(64), nullable=True),
        sa.Column("legacy_route", sa.String(10), nullable=True),
        sa.Column("legacy_routing_reason", sa.String(255), nullable=True),
        sa.Column("legacy_cache_hit", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("legacy_cache_id", UUID(as_uuid=True), nullable=True),
        sa.Column("legacy_answer", sa.Text(), nullable=False),
        sa.Column("legacy_sources", JSONB(), nullable=False, server_default="[]"),
        sa.Column("legacy_answer_path", sa.String(64), nullable=True),
        sa.Column("legacy_latency_ms", sa.Float(), nullable=False, server_default="0"),
        sa.Column("agentic_cache_bypassed", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("agentic_tools_called", JSONB(), nullable=False, server_default="[]"),
        sa.Column("agentic_tool_results", JSONB(), nullable=True),
        sa.Column("agentic_answer", sa.Text(), nullable=False),
        sa.Column("agentic_sources", JSONB(), nullable=False, server_default="[]"),
        sa.Column("agentic_error", sa.Text(), nullable=True),
        sa.Column("agentic_latency_ms", sa.Float(), nullable=False, server_default="0"),
        sa.Column("quality_comparable", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("match_score", sa.Float(), nullable=True),
        sa.Column("answer_match", sa.Boolean(), nullable=True),
        sa.Column("compound_case_pass", sa.Boolean(), nullable=True),
        sa.Column("safety_critical_case", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("human_review_flag", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("comparator_notes", sa.Text(), nullable=True),
    )
    op.create_index("ix_shadow_routing_log_asked_at", "shadow_routing_log", ["asked_at"])
    op.create_index(
        "ix_shadow_routing_log_quality_comparable",
        "shadow_routing_log",
        ["quality_comparable"],
    )
    op.create_index(
        "ix_shadow_routing_log_safety_critical",
        "shadow_routing_log",
        ["safety_critical_case"],
    )


def downgrade() -> None:
    if not _routing_mode_enabled():
        return
    op.drop_index("ix_shadow_routing_log_safety_critical", table_name="shadow_routing_log")
    op.drop_index("ix_shadow_routing_log_quality_comparable", table_name="shadow_routing_log")
    op.drop_index("ix_shadow_routing_log_asked_at", table_name="shadow_routing_log")
    op.drop_table("shadow_routing_log")
