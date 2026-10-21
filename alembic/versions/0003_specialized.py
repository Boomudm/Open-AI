"""P2 specialized: drawings, certificates, inspections, incidents

Revision ID: 0003_specialized
Revises: 0002_chat
Create Date: 2026-05-24
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_specialized"
down_revision: Union[str, None] = "0002_chat"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "drawings",
        sa.Column("drawing_id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("doc_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("documents.doc_id", ondelete="CASCADE"), nullable=False),
        sa.Column("machine_id", sa.String(20),
                  sa.ForeignKey("machines.machine_id"), nullable=False),
        sa.Column("drawing_no", sa.String(100)),
        sa.Column("drawing_type", sa.String(50)),
        sa.Column("parts", postgresql.JSONB),
        sa.Column("canvas_width", sa.Integer),
        sa.Column("canvas_height", sa.Integer),
    )
    op.create_index("ix_drawings_machine", "drawings", ["machine_id"])
    op.execute("CREATE INDEX ix_drawings_parts ON drawings USING gin (parts jsonb_path_ops)")

    op.create_table(
        "certificates",
        sa.Column("cert_id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("doc_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("documents.doc_id", ondelete="CASCADE"), nullable=False),
        sa.Column("machine_id", sa.String(20), sa.ForeignKey("machines.machine_id")),
        sa.Column("cert_no", sa.String(100)),
        sa.Column("issuer", sa.String(200)),
        sa.Column("scope", sa.Text),
        sa.Column("issued_date", sa.Date),
        sa.Column("expiry_date", sa.Date, nullable=False),
    )
    op.create_index("ix_certificates_expiry", "certificates", ["expiry_date"])

    op.create_table(
        "inspections",
        sa.Column("inspection_id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("doc_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("documents.doc_id", ondelete="CASCADE"), nullable=False),
        sa.Column("machine_id", sa.String(20),
                  sa.ForeignKey("machines.machine_id"), nullable=False),
        sa.Column("inspector", sa.String(100)),
        sa.Column("inspection_date", sa.Date, nullable=False),
        sa.Column("result", sa.String(20)),
        sa.Column("findings", postgresql.JSONB),
    )
    op.create_index(
        "ix_inspections_machine_date", "inspections", ["machine_id", "inspection_date"]
    )

    op.create_table(
        "incidents",
        sa.Column("incident_id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("doc_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("documents.doc_id", ondelete="SET NULL")),
        sa.Column("machine_id", sa.String(20),
                  sa.ForeignKey("machines.machine_id"), nullable=False),
        sa.Column("incident_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("severity", sa.String(20)),
        sa.Column("incident_type", sa.String(30)),
        sa.Column("description", sa.Text),
        sa.Column("status", sa.String(20), server_default="open"),
    )
    op.create_index("ix_incidents_machine", "incidents", ["machine_id"])


def downgrade() -> None:
    for tbl in ["incidents", "inspections", "certificates", "drawings"]:
        op.execute(f'DROP TABLE IF EXISTS "{tbl}" CASCADE')
