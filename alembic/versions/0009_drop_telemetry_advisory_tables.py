"""Drop telemetry_events + optimization_advisories — UC6 removed.

Revision ID: 0009_drop_telemetry_advisory
Revises: 0008_drop_sensor_tables
Create Date: 2026-05-29
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0009_drop_telemetry_advisory"
down_revision: Union[str, None] = "0008_drop_sensor_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index("ix_advisory_machine_time", table_name="optimization_advisories")
    op.drop_table("optimization_advisories")
    op.drop_index("ix_telemetry_machine_time", table_name="telemetry_events")
    op.drop_table("telemetry_events")


def downgrade() -> None:
    import sqlalchemy as sa
    from sqlalchemy.dialects import postgresql

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
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_telemetry_machine_time",
        "telemetry_events",
        ["machine_id", "received_at"],
    )
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
        sa.Column(
            "emitted_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("acknowledged", sa.Boolean, server_default="false"),
        sa.Column("acknowledged_by", sa.String(100)),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True)),
    )
    op.create_index(
        "ix_advisory_machine_time",
        "optimization_advisories",
        ["machine_id", "emitted_at"],
    )
