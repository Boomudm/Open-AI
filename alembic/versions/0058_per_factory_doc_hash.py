"""Scope document content-hash uniqueness to the factory.

Revision ID: 0058_per_factory_doc_hash
Revises: 0057_rag_only_cleanup
Create Date: 2026-07-08

The original ``ux_documents_hash`` unique index keyed on ``file_hash_sha256``
alone, so a given file could physically exist only once across the whole system.
That forced a re-upload into another factory to *relocate* the existing document
across the tenant boundary (a data-isolation break). Scope uniqueness to
``(factory_id, file_hash_sha256)`` so the same file can live as an independent
document in each factory while duplicates within a factory still dedup.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0058_per_factory_doc_hash"
down_revision: Union[str, None] = "0057_rag_only_cleanup"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ux_documents_hash")
    op.execute(
        "CREATE UNIQUE INDEX ux_documents_factory_hash "
        "ON documents (factory_id, file_hash_sha256) "
        "WHERE file_hash_sha256 IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ux_documents_factory_hash")
    op.execute(
        "CREATE UNIQUE INDEX ux_documents_hash "
        "ON documents (file_hash_sha256) "
        "WHERE file_hash_sha256 IS NOT NULL"
    )
