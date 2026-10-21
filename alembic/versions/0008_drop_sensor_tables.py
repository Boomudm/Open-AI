"""Drop sensor_readings + alert_rules — machine sensor API removed.

Revision ID: 0008_drop_sensor_tables
Revises: 0007_production_events
Create Date: 2026-05-29
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0008_drop_sensor_tables"
down_revision: Union[str, None] = "0007_production_events"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table("alert_rules")
    op.drop_index("ix_sensor_machine_metric_time", table_name="sensor_readings")
    op.drop_table("sensor_readings")


def downgrade() -> None:
    import sqlalchemy as sa
    from sqlalchemy.dialects import postgresql

    op.create_table(
        "sensor_readings",
        sa.Column(
            "reading_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuid_generate_v4()"),
        ),
        sa.Column("machine_id", sa.String(20), sa.ForeignKey("machines.machine_id"), nullable=False),
        sa.Column("metric", sa.String(50), nullable=False),
        sa.Column("value", sa.Numeric(12, 4), nullable=False),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_sensor_machine_metric_time",
        "sensor_readings",
        ["machine_id", "metric", "recorded_at"],
    )
    op.create_table(
        "alert_rules",
        sa.Column(
            "rule_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuid_generate_v4()"),
        ),
        sa.Column("machine_id", sa.String(20), sa.ForeignKey("machines.machine_id")),
        sa.Column("metric", sa.String(50), nullable=False),
        sa.Column("op", sa.String(10), nullable=False),
        sa.Column("threshold", sa.Numeric(12, 4), nullable=False),
        sa.Column("severity", sa.String(20), server_default="warning"),
        sa.Column("enabled", sa.Boolean, server_default="true"),
        sa.Column("message_template", sa.Text),
    )
