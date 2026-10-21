"""P3 inventory: spare_parts, spare_part_machines, stock_movements, purchase_orders, po_lines

Revision ID: 0004_inventory
Revises: 0003_specialized
Create Date: 2026-05-24
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_inventory"
down_revision: Union[str, None] = "0003_specialized"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "spare_parts",
        sa.Column("part_id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("part_no", sa.String(100), unique=True, nullable=False),
        sa.Column("part_name", sa.String(200), nullable=False),
        sa.Column("manufacturer", sa.String(100)),
        sa.Column("unit_cost_thb", sa.Numeric(12, 2)),
        sa.Column("lead_time_days", sa.Integer),
        sa.Column("min_stock", sa.Integer, server_default="0"),
        sa.Column("current_stock", sa.Integer, server_default="0"),
        sa.Column("notes", sa.Text),
    )

    op.create_table(
        "spare_part_machines",
        sa.Column("part_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("spare_parts.part_id", ondelete="CASCADE"), primary_key=True),
        sa.Column("machine_id", sa.String(20),
                  sa.ForeignKey("machines.machine_id", ondelete="CASCADE"), primary_key=True),
        sa.Column("component_id", sa.String(30), sa.ForeignKey("components.component_id")),
    )

    op.create_table(
        "stock_movements",
        sa.Column("movement_id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("part_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("spare_parts.part_id")),
        sa.Column("movement_type", sa.String(20)),
        sa.Column("qty", sa.Integer, nullable=False),
        sa.Column("work_order_id", sa.String(30), sa.ForeignKey("work_orders.work_order_id")),
        sa.Column("moved_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("notes", sa.Text),
    )
    op.create_index("ix_stock_part_date", "stock_movements", ["part_id", "moved_at"])

    op.create_table(
        "purchase_orders",
        sa.Column("po_no", sa.String(50), primary_key=True),
        sa.Column("vendor", sa.String(200)),
        sa.Column("issued_date", sa.Date),
        sa.Column("total_thb", sa.Numeric(14, 2)),
        sa.Column("status", sa.String(20)),
    )

    op.create_table(
        "po_lines",
        sa.Column("po_line_id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("po_no", sa.String(50),
                  sa.ForeignKey("purchase_orders.po_no", ondelete="CASCADE")),
        sa.Column("part_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("spare_parts.part_id")),
        sa.Column("qty", sa.Integer),
        sa.Column("unit_price_thb", sa.Numeric(12, 2)),
    )
    op.create_index("ix_po_lines_po", "po_lines", ["po_no"])


def downgrade() -> None:
    for tbl in [
        "po_lines",
        "purchase_orders",
        "stock_movements",
        "spare_part_machines",
        "spare_parts",
    ]:
        op.execute(f'DROP TABLE IF EXISTS "{tbl}" CASCADE')
