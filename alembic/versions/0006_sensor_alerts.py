"""Sensor readings + alert rules for rule-based SSE alerts (issue #62)

Revision ID: 0006_sensor_alerts
Revises: 0005_partition_repair_history
Create Date: 2026-05-24
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006_sensor_alerts"
down_revision: Union[str, None] = "0005_partition_repair_history"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
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


def downgrade() -> None:
    op.drop_table("alert_rules")
    op.drop_index("ix_sensor_machine_metric_time", table_name="sensor_readings")
    op.drop_table("sensor_readings")
