"""Job positions and document position ACL

Revision ID: 0021_job_positions_and_document_acl
Revises: 0020_verified_qa_cache
Create Date: 2026-06-11
"""
from __future__ import annotations

import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0021_job_positions_acl"
down_revision: Union[str, None] = "0020_verified_qa_cache"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SEED_POSITIONS: list[tuple[str, str, str, int]] = [
    ("qc", "เจ้าหน้าที่ควบคุมคุณภาพ (QC)", "Quality Control", 10),
    ("qa", "เจ้าหน้าที่ประกันคุณภาพ (QA)", "Quality Assurance", 20),
    (
        "maintenance_tech",
        "ช่างเทคนิค / ช่างซ่อมบำรุง",
        "Maintenance Technician",
        30,
    ),
    (
        "maintenance_engineer",
        "วิศวกรซ่อมบำรุง",
        "Maintenance Engineer",
        40,
    ),
    ("safety", "เจ้าหน้าที่ความปลอดภัย", "Safety Officer", 50),
    ("warehouse", "เจ้าหน้าที่คลังสินค้า", "Warehouse Staff", 60),
    ("hr_admin", "ฝ่ายบุคคลและธุรการ", "HR and Administration", 70),
    ("production_manager", "Production Manager", "Production Manager", 80),
    ("supervisor", "Supervisor / Foreman", "Supervisor / Foreman", 90),
]


def upgrade() -> None:
    op.create_table(
        "job_positions",
        sa.Column("position_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("position_code", sa.String(50), nullable=False, unique=True),
        sa.Column("name_th", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    op.create_table(
        "user_job_positions",
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.user_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "position_id",
            UUID(as_uuid=True),
            sa.ForeignKey("job_positions.position_id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )

    op.create_table(
        "document_job_positions",
        sa.Column(
            "doc_id",
            UUID(as_uuid=True),
            sa.ForeignKey("documents.doc_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "position_id",
            UUID(as_uuid=True),
            sa.ForeignKey("job_positions.position_id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )
    op.create_index(
        "ix_document_job_positions_doc_id",
        "document_job_positions",
        ["doc_id"],
    )

    job_positions = sa.table(
        "job_positions",
        sa.column("position_id", UUID(as_uuid=True)),
        sa.column("position_code", sa.String),
        sa.column("name_th", sa.String),
        sa.column("description", sa.Text),
        sa.column("is_active", sa.Boolean),
        sa.column("sort_order", sa.Integer),
    )
    op.bulk_insert(
        job_positions,
        [
            {
                "position_id": uuid.uuid4(),
                "position_code": code,
                "name_th": name_th,
                "description": desc,
                "is_active": True,
                "sort_order": sort_order,
            }
            for code, name_th, desc, sort_order in SEED_POSITIONS
        ],
    )


def downgrade() -> None:
    op.drop_index("ix_document_job_positions_doc_id", table_name="document_job_positions")
    op.drop_table("document_job_positions")
    op.drop_table("user_job_positions")
    op.drop_table("job_positions")
