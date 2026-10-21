"""Production event persistence — telemetry, advisories, alerts, inventory reports

Revision ID: 0007_production_events
Revises: 0006_sensor_alerts
Create Date: 2026-05-25
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007_production_events"
down_revision: Union[str, None] = "0006_sensor_alerts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "telemetry_events",
        sa.Column(
            "event_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuid_generate_v4()"),
        ),
        sa.Column("machine_id", sa.String(20), sa.ForeignKey("machines.machine_id"), nullable=False),
        sa.Column("factory_id", sa.String(20), sa.ForeignKey("factories.factory_id")),
        sa.Column("payload", postgresql.JSONB, nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_telemetry_machine_time", "telemetry_events", ["machine_id", "received_at"])

    op.create_table(
        "optimization_advisories",
        sa.Column("advisory_id", sa.String(64), primary_key=True),
        sa.Column("machine_id", sa.String(20), sa.ForeignKey("machines.machine_id"), nullable=False),
        sa.Column("factory_id", sa.String(20), sa.ForeignKey("factories.factory_id")),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("trigger", postgresql.JSONB, nullable=False),
        sa.Column("product", postgresql.JSONB, nullable=False),
        sa.Column("recommendation", postgresql.JSONB, nullable=False),
        sa.Column("sources", postgresql.JSONB, server_default="[]"),
        sa.Column("emitted_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("acknowledged", sa.Boolean, server_default="false"),
        sa.Column("acknowledged_by", sa.String(100)),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_advisory_machine_time", "optimization_advisories", ["machine_id", "emitted_at"])

    op.create_table(
        "alert_records",
        sa.Column("alert_id", sa.String(64), primary_key=True),
        sa.Column("alert_type", sa.String(50), nullable=False),
        sa.Column("machine_id", sa.String(20), sa.ForeignKey("machines.machine_id"), nullable=False),
        sa.Column("factory_id", sa.String(20), sa.ForeignKey("factories.factory_id")),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("message", sa.Text, nullable=False),
        sa.Column("metric", sa.String(50)),
        sa.Column("value", sa.Float),
        sa.Column("threshold", sa.Float),
        sa.Column("risk_score", sa.Float),
        sa.Column("reason", sa.Text),
        sa.Column("severity_zone", sa.String(20)),
        sa.Column("mcp_tools", postgresql.JSONB),
        sa.Column("emitted_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("acknowledged", sa.Boolean, server_default="false"),
        sa.Column("acknowledged_by", sa.String(100)),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_alert_machine_time", "alert_records", ["machine_id", "emitted_at"])

    op.create_table(
        "inventory_reports",
        sa.Column(
            "report_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuid_generate_v4()"),
        ),
        sa.Column("factory_id", sa.String(20), sa.ForeignKey("factories.factory_id")),
        sa.Column("status", sa.String(20), server_default="pending"),
        sa.Column("backend", sa.String(30), server_default="native"),
        sa.Column("markdown", sa.Text),
        sa.Column("error", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
    )


def downgrade() -> None:
    op.drop_table("inventory_reports")
    op.drop_index("ix_alert_machine_time", table_name="alert_records")
    op.drop_table("alert_records")
    op.drop_index("ix_advisory_machine_time", table_name="optimization_advisories")
    op.drop_table("optimization_advisories")
    op.drop_index("ix_telemetry_machine_time", table_name="telemetry_events")
    op.drop_table("telemetry_events")
