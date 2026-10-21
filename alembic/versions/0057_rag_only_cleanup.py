"""Phase 1 RAG-only: drop analytics/inventory/insights tables.

Revision ID: 0057_rag_only_cleanup
Revises: 0056_external_table_scope
Create Date: 2026-07-04

Keeps ``repair_history`` for RAG ingest. Drops work orders, inventory,
alerts, and question analytics tables removed in Phase 1.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0057_rag_only_cleanup"
down_revision: Union[str, None] = "0056_external_table_scope"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_DROP_TABLES = (
    "question_analytics",
    "inventory_reports",
    "alert_records",
    "reorder_requests",
    "po_lines",
    "stock_movements_legacy",
    "stock_movements",
    "spare_part_machines",
    "work_orders",
    "spare_parts",
    "purchase_orders",
)


def upgrade() -> None:
    op.execute(
        "ALTER TABLE IF EXISTS repair_history "
        "DROP CONSTRAINT IF EXISTS repair_history_work_order_id_fkey"
    )
    for table in _DROP_TABLES:
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")


def downgrade() -> None:
    raise NotImplementedError(
        "0057_rag_only_cleanup downgrade is not supported — restore from backup."
    )
