"""Ingestion jobs survive document deletion (audit trail for NOC Ingest Jobs chart).

Revision ID: 0055_ingest_job_doc_setnull
Revises: 0054_external_data_sources
Create Date: 2026-07-02

Deleting a document previously cascade-deleted its ingestion_jobs rows,
which erased its ingest history from the system-admin dashboard's
Ingest Jobs chart with no trace. Switch the FK to ON DELETE SET NULL so
the job row survives, and the delete-document endpoint now marks
surviving jobs with status='deleted' before detaching them so the chart
can render deletions as their own category.
"""

from __future__ import annotations

from alembic import op

revision = "0055_ingest_job_doc_setnull"
down_revision = "0054_external_data_sources"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ingestion_jobs_doc_id_fkey", "ingestion_jobs", type_="foreignkey")
    op.create_foreign_key(
        "ingestion_jobs_doc_id_fkey",
        "ingestion_jobs",
        "documents",
        ["doc_id"],
        ["doc_id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("ingestion_jobs_doc_id_fkey", "ingestion_jobs", type_="foreignkey")
    op.create_foreign_key(
        "ingestion_jobs_doc_id_fkey",
        "ingestion_jobs",
        "documents",
        ["doc_id"],
        ["doc_id"],
        ondelete="CASCADE",
    )
