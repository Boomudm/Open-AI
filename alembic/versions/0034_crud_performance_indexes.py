"""CRUD performance indexes for millisecond list/filter latency.

Revision ID: 0034_crud_performance_indexes
Revises: 0033_parent_child_chunks
Create Date: 2026-06-19
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0034_crud_performance_indexes"
down_revision: Union[str, None] = "0033_parent_child_chunks"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_chat_sessions_user_updated",
        "chat_sessions",
        ["user_id", sa.text("updated_at DESC")],
    )
    op.create_index("ix_documents_factory_id", "documents", ["factory_id"])
    op.create_index(
        "ix_documents_factory_ingest",
        "documents",
        ["factory_id", "ingest_status"],
    )
    op.create_index("ix_ingestion_jobs_doc_id", "ingestion_jobs", ["doc_id"])
    op.create_index(
        "ix_spare_part_machines_machine_id",
        "spare_part_machines",
        ["machine_id"],
    )
    op.create_index(
        "ix_user_job_positions_position_id",
        "user_job_positions",
        ["position_id"],
    )
    op.create_index(
        "ix_document_job_positions_position_id",
        "document_job_positions",
        ["position_id"],
    )
    op.create_index(
        "ix_alert_records_factory_emitted",
        "alert_records",
        ["factory_id", sa.text("emitted_at DESC")],
    )
    op.create_index(
        "ix_work_orders_factory_issued",
        "work_orders",
        ["factory_id", sa.text("issued_date DESC")],
    )
    op.create_index(
        "ix_ingestion_jobs_status_created",
        "ingestion_jobs",
        ["status", sa.text("created_at DESC")],
    )
    op.execute(
        "CREATE INDEX ix_verified_qa_cache_source_doc_ids "
        "ON verified_qa_cache USING GIN (source_doc_ids)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_verified_qa_cache_source_doc_ids")
    op.drop_index("ix_ingestion_jobs_status_created", table_name="ingestion_jobs")
    op.drop_index("ix_work_orders_factory_issued", table_name="work_orders")
    op.drop_index("ix_alert_records_factory_emitted", table_name="alert_records")
    op.drop_index("ix_document_job_positions_position_id", table_name="document_job_positions")
    op.drop_index("ix_user_job_positions_position_id", table_name="user_job_positions")
    op.drop_index("ix_spare_part_machines_machine_id", table_name="spare_part_machines")
    op.drop_index("ix_ingestion_jobs_doc_id", table_name="ingestion_jobs")
    op.drop_index("ix_documents_factory_ingest", table_name="documents")
    op.drop_index("ix_documents_factory_id", table_name="documents")
    op.drop_index("ix_chat_sessions_user_updated", table_name="chat_sessions")
