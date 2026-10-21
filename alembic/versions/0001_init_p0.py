"""P0 init: org, components, documents, document_chunks, maintenance, ingestion observability

Revision ID: 0001_init_p0
Revises:
Create Date: 2026-05-24
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_init_p0"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
    op.execute('CREATE EXTENSION IF NOT EXISTS "pg_trgm"')

    # ── RBAC (schema only) ───────────────────────────────────────────────
    op.create_table(
        "roles",
        sa.Column("role_id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("role_code", sa.String(30), nullable=False, unique=True),
        sa.Column("description", sa.Text),
    )
    op.create_table(
        "users",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("username", sa.String(50), nullable=False, unique=True),
        sa.Column("full_name", sa.String(100)),
        sa.Column("email", sa.String(120)),
        sa.Column("password_hash", sa.String(255)),
        sa.Column("is_active", sa.Boolean, server_default=sa.text("TRUE")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_table(
        "user_roles",
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.user_id", ondelete="CASCADE"), primary_key=True),
        sa.Column("role_id", sa.Integer,
                  sa.ForeignKey("roles.role_id", ondelete="CASCADE"), primary_key=True),
    )

    # ── Org ──────────────────────────────────────────────────────────────
    op.create_table(
        "factories",
        sa.Column("factory_id", sa.String(20), primary_key=True),
        sa.Column("factory_name", sa.String(100), nullable=False),
        sa.Column("location", sa.String(200)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_table(
        "user_factory_access",
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.user_id", ondelete="CASCADE"), primary_key=True),
        sa.Column("factory_id", sa.String(20),
                  sa.ForeignKey("factories.factory_id", ondelete="CASCADE"), primary_key=True),
        sa.Column("access_level", sa.String(20), server_default="read"),
    )
    op.create_table(
        "machines",
        sa.Column("machine_id", sa.String(20), primary_key=True),
        sa.Column("factory_id", sa.String(20), sa.ForeignKey("factories.factory_id"), nullable=False),
        sa.Column("machine_name", sa.String(100), nullable=False),
        sa.Column("machine_type", sa.String(50)),
        sa.Column("manufacturer", sa.String(100)),
        sa.Column("model_number", sa.String(100)),
        sa.Column("install_date", sa.Date),
        sa.Column("is_active", sa.Boolean, server_default=sa.text("TRUE")),
        sa.Column("notes", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_machines_factory", "machines", ["factory_id"])
    op.execute("CREATE INDEX ix_machines_name_trgm ON machines USING gin (machine_name gin_trgm_ops)")

    op.create_table(
        "machine_aliases",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("machine_id", sa.String(20),
                  sa.ForeignKey("machines.machine_id", ondelete="CASCADE"), nullable=False),
        sa.Column("alias", sa.String(100), nullable=False),
        sa.Column("source", sa.String(50)),
        sa.Column("confidence", sa.Numeric(3, 2), server_default="1.00"),
    )
    op.execute(
        "CREATE INDEX ix_machine_aliases_alias_trgm ON machine_aliases "
        "USING gin (alias gin_trgm_ops)"
    )
    op.execute(
        "CREATE UNIQUE INDEX ux_machine_aliases_norm ON machine_aliases "
        "(lower(alias), machine_id)"
    )

    op.create_table(
        "components",
        sa.Column("component_id", sa.String(30), primary_key=True),
        sa.Column("machine_id", sa.String(20),
                  sa.ForeignKey("machines.machine_id"), nullable=False),
        sa.Column("parent_component_id", sa.String(30),
                  sa.ForeignKey("components.component_id")),
        sa.Column("component_name", sa.String(100), nullable=False),
        sa.Column("component_type", sa.String(50)),
        sa.Column("manufacturer", sa.String(100)),
        sa.Column("part_number", sa.String(100)),
        sa.Column("install_date", sa.Date),
        sa.Column("depth", sa.SmallInteger, nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean, server_default=sa.text("TRUE")),
        sa.Column("notes", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.CheckConstraint("depth BETWEEN 0 AND 2", name="ck_components_depth"),
    )
    op.create_index("ix_components_machine", "components", ["machine_id"])
    op.create_index("ix_components_parent", "components", ["parent_component_id"])

    op.create_table(
        "component_aliases",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("component_id", sa.String(30),
                  sa.ForeignKey("components.component_id", ondelete="CASCADE"), nullable=False),
        sa.Column("alias", sa.String(100), nullable=False),
        sa.Column("source", sa.String(50)),
    )
    op.execute(
        "CREATE INDEX ix_component_aliases_alias_trgm ON component_aliases "
        "USING gin (alias gin_trgm_ops)"
    )

    # ── Documents ────────────────────────────────────────────────────────
    op.create_table(
        "documents",
        sa.Column("doc_id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("factory_id", sa.String(20), sa.ForeignKey("factories.factory_id")),
        sa.Column("machine_id", sa.String(20), sa.ForeignKey("machines.machine_id")),
        sa.Column("component_id", sa.String(30), sa.ForeignKey("components.component_id")),
        sa.Column("document_category", sa.String(30), nullable=False),
        sa.Column("document_type", sa.String(50), nullable=False),
        sa.Column("title", sa.String(500)),
        sa.Column("language", sa.String(10), server_default="th"),
        sa.Column("revision", sa.String(30)),
        sa.Column("effective_date", sa.Date),
        sa.Column("expiry_date", sa.Date),
        sa.Column("source_file", sa.String(500), nullable=False),
        sa.Column("storage_uri", sa.String(1000)),
        sa.Column("file_hash_sha256", sa.String(64)),
        sa.Column("file_size_bytes", sa.BigInteger),
        sa.Column("page_count", sa.Integer),
        sa.Column("ingest_status", sa.String(20), server_default="pending"),
        sa.Column("chunks_count", sa.Integer, server_default="0"),
        sa.Column("extra_metadata", postgresql.JSONB),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.user_id")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_documents_machine", "documents", ["machine_id"])
    op.create_index("ix_documents_category_type", "documents", ["document_category", "document_type"])
    op.create_index("ix_documents_status", "documents", ["ingest_status"])
    op.execute(
        "CREATE UNIQUE INDEX ux_documents_hash ON documents (file_hash_sha256) "
        "WHERE file_hash_sha256 IS NOT NULL"
    )

    op.create_table(
        "document_chunks",
        sa.Column("chunk_id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("doc_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("documents.doc_id", ondelete="CASCADE"), nullable=False),
        sa.Column("qdrant_point_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("chunk_index", sa.Integer, nullable=False),
        sa.Column("page", sa.Integer),
        sa.Column("char_count", sa.Integer),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_chunks_doc", "document_chunks", ["doc_id"])
    op.create_index("ux_chunks_qdrant", "document_chunks", ["qdrant_point_id"], unique=True)

    # ── Maintenance (P0) ─────────────────────────────────────────────────
    op.create_table(
        "work_orders",
        sa.Column("work_order_id", sa.String(30), primary_key=True),
        sa.Column("factory_id", sa.String(20), sa.ForeignKey("factories.factory_id")),
        sa.Column("machine_id", sa.String(20), sa.ForeignKey("machines.machine_id"), nullable=False),
        sa.Column("component_id", sa.String(30), sa.ForeignKey("components.component_id")),
        sa.Column("issued_date", sa.Date, nullable=False),
        sa.Column("status", sa.String(20), server_default="open"),
        sa.Column("priority", sa.String(10), server_default="medium"),
        sa.Column("description", sa.Text),
        sa.Column("assigned_to", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.user_id")),
        sa.Column("closed_date", sa.Date),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_wo_machine", "work_orders", ["machine_id"])
    op.create_index("ix_wo_status", "work_orders", ["status"])

    op.create_table(
        "repair_history",
        sa.Column("repair_id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("doc_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("documents.doc_id", ondelete="SET NULL")),
        sa.Column("work_order_id", sa.String(30), sa.ForeignKey("work_orders.work_order_id")),
        sa.Column("machine_id", sa.String(20), sa.ForeignKey("machines.machine_id"), nullable=False),
        sa.Column("component_id", sa.String(30), sa.ForeignKey("components.component_id")),
        sa.Column("machine_label", sa.String(100)),
        sa.Column("repair_date", sa.DateTime(timezone=True)),
        sa.Column("symptom", sa.Text),
        sa.Column("root_cause", sa.Text),
        sa.Column("solution", sa.Text),
        sa.Column("result", sa.Text),
        sa.Column("downtime_hours", sa.Numeric(6, 2)),
        sa.Column("cost_thb", sa.Numeric(12, 2)),
        sa.Column("narrative", sa.Text),
        sa.Column("source_file", sa.String(255)),
        sa.Column("source_sheet", sa.String(100)),
        sa.Column("row_number", sa.Integer),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_repair_machine_date", "repair_history", ["machine_id", "repair_date"])
    op.create_index("ix_repair_component", "repair_history", ["component_id"])

    # ── Ingestion observability ──────────────────────────────────────────
    op.create_table(
        "ingestion_jobs",
        sa.Column("job_id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("doc_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("documents.doc_id", ondelete="CASCADE")),
        sa.Column("document_type", sa.String(50), nullable=False),
        sa.Column("celery_task_id", sa.String(60)),
        sa.Column("status", sa.String(20), server_default="queued"),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("rows_total", sa.Integer, server_default="0"),
        sa.Column("rows_ok", sa.Integer, server_default="0"),
        sa.Column("rows_skipped", sa.Integer, server_default="0"),
        sa.Column("error_message", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_jobs_status", "ingestion_jobs", ["status"])

    op.create_table(
        "ingestion_errors",
        sa.Column("error_id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("job_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("ingestion_jobs.job_id", ondelete="CASCADE")),
        sa.Column("row_number", sa.Integer),
        sa.Column("chunk_index", sa.Integer),
        sa.Column("reason_code", sa.String(50)),
        sa.Column("reason_detail", sa.Text),
        sa.Column("raw_payload", postgresql.JSONB),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_ing_err_job", "ingestion_errors", ["job_id"])


def downgrade() -> None:
    for tbl in [
        "ingestion_errors", "ingestion_jobs",
        "repair_history", "work_orders",
        "document_chunks", "documents",
        "component_aliases", "components",
        "machine_aliases", "machines",
        "user_factory_access", "factories",
        "user_roles", "users", "roles",
    ]:
        op.execute(f'DROP TABLE IF EXISTS "{tbl}" CASCADE')
