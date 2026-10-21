"""P3 scale: convert repair_history and stock_movements to RANGE partitions

Strategy: keep current tables as `*_legacy`, create new partitioned parents,
copy data, atomically rename. Stock movements partition monthly, repair history
yearly. Run during a maintenance window.

Revision ID: 0005_partition_repair_history
Revises: 0004_inventory
Create Date: 2026-05-24
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0005_partition_repair_history"
down_revision: Union[str, None] = "0004_inventory"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── repair_history → yearly RANGE partition ───────────────────────────
    op.execute("ALTER TABLE repair_history RENAME TO repair_history_legacy;")
    # rename legacy indexes so the names are free for the new partitioned table
    op.execute("ALTER INDEX IF EXISTS ix_repair_machine_date RENAME TO ix_repair_machine_date_legacy;")
    op.execute("ALTER INDEX IF EXISTS ix_repair_component RENAME TO ix_repair_component_legacy;")
    op.execute(
        """
        CREATE TABLE repair_history (
            LIKE repair_history_legacy INCLUDING ALL EXCLUDING INDEXES EXCLUDING CONSTRAINTS
        ) PARTITION BY RANGE (repair_date);
        """
    )
    for year in (2024, 2025, 2026, 2027):
        op.execute(
            f"""
            CREATE TABLE repair_history_y{year}
                PARTITION OF repair_history
                FOR VALUES FROM ('{year}-01-01') TO ('{year + 1}-01-01');
            """
        )
    op.execute(
        """
        CREATE INDEX ix_repair_machine_date ON repair_history (machine_id, repair_date DESC);
        CREATE INDEX ix_repair_component ON repair_history (component_id);
        """
    )
    op.execute(
        """
        INSERT INTO repair_history SELECT * FROM repair_history_legacy
            WHERE repair_date IS NOT NULL;
        """
    )

    # ── stock_movements → monthly RANGE partition ─────────────────────────
    op.execute("ALTER TABLE stock_movements RENAME TO stock_movements_legacy;")
    op.execute("ALTER INDEX IF EXISTS ix_stock_part_date RENAME TO ix_stock_part_date_legacy;")
    op.execute(
        """
        CREATE TABLE stock_movements (
            LIKE stock_movements_legacy INCLUDING ALL EXCLUDING INDEXES EXCLUDING CONSTRAINTS
        ) PARTITION BY RANGE (moved_at);
        """
    )
    for year in (2025, 2026, 2027):
        for month in range(1, 13):
            start = f"{year}-{month:02d}-01"
            next_year = year + (1 if month == 12 else 0)
            next_month = 1 if month == 12 else month + 1
            end = f"{next_year}-{next_month:02d}-01"
            part = f"stock_movements_y{year}m{month:02d}"
            op.execute(
                f"CREATE TABLE {part} PARTITION OF stock_movements "
                f"FOR VALUES FROM ('{start}') TO ('{end}');"
            )
    op.execute("CREATE INDEX ix_stock_part_date ON stock_movements (part_id, moved_at DESC);")
    op.execute("INSERT INTO stock_movements SELECT * FROM stock_movements_legacy;")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS stock_movements CASCADE;")
    op.execute("ALTER TABLE stock_movements_legacy RENAME TO stock_movements;")
    op.execute("ALTER INDEX IF EXISTS ix_stock_part_date_legacy RENAME TO ix_stock_part_date;")
    op.execute("DROP TABLE IF EXISTS repair_history CASCADE;")
    op.execute("ALTER TABLE repair_history_legacy RENAME TO repair_history;")
    op.execute("ALTER INDEX IF EXISTS ix_repair_machine_date_legacy RENAME TO ix_repair_machine_date;")
    op.execute("ALTER INDEX IF EXISTS ix_repair_component_legacy RENAME TO ix_repair_component;")
