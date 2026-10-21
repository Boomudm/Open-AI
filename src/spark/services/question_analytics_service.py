"""RAG-only stub — question analytics persistence disabled."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from spark.services.rag_service import RAGFilter


async def record_question_analytics(
    db: AsyncSession,
    *,
    message_id: uuid.UUID,
    question: str,
    intent: str,
    merged_filter: RAGFilter,
    asked_at: datetime | None = None,
) -> None:
    del db, message_id, question, intent, merged_filter, asked_at
    return None
