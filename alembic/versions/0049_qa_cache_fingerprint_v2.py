"""Phase 12 — invalidate verified Q&A cache after fingerprint v2 dimensions."""

from __future__ import annotations

from alembic import op

revision = "0049_qa_cache_fingerprint_v2"
down_revision = "0048_rag_scope_broadening_audit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DELETE FROM verified_qa_cache")


def downgrade() -> None:
    pass
