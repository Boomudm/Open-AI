from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from spark.ingestion.parsers.base import ParsedRecord

ALLOWED_POSTGRES_TABLES = frozenset()


class PostgresRouter:
    """Document-only RAG does not write structured records."""

    async def write(
        self,
        records: list[ParsedRecord],
        doc_id: uuid.UUID,
        config: dict[str, Any],
        document_context: dict[str, Any],
        session: AsyncSession,
    ) -> int:
        del records, doc_id, config, document_context, session
        return 0
