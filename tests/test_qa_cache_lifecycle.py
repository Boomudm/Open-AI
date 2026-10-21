"""Q&A cache lifecycle: verify → hit → re-ingest invalidate → miss."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from spark.core.config import settings
from spark.core.database import AsyncSessionLocal
from spark.core.security import Principal
from spark.db.models.chat import ChatMessage, ChatSession
from spark.db.models.docs import Document
from spark.services.qa_cache_service import qa_cache_service


@pytest.mark.asyncio
async def test_cache_verify_hit_invalidate_miss(monkeypatch) -> None:
    monkeypatch.setattr(settings, "qa_cache_enabled", True)
    session_id = uuid.uuid4()
    factory_id = "F-01"
    question = f"bearing model MC-001 lifecycle {uuid.uuid4().hex[:8]}"

    async with AsyncSessionLocal() as db:
        doc = (await db.execute(select(Document).limit(1))).scalar_one_or_none()
        if doc is None:
            pytest.skip("requires at least one document in database")

        chat_session = ChatSession(session_id=session_id, title="cache lifecycle")
        db.add(chat_session)
        await db.flush()
        message = ChatMessage(
            session_id=session_id,
            role="assistant",
            content="SKF 6205-2RS",
            sources=[{"doc_id": str(doc.doc_id), "score": 0.9}],
        )
        db.add(message)
        await db.flush()

        principal = Principal(
            user_id="00000000-0000-0000-0000-000000000001",
            username="admin",
            roles=("admin",),
            factory_access={factory_id: "admin"},
        )
        await qa_cache_service.verify_message(
            db,
            message=message,
            factory_id=factory_id,
            question_text=question,
            principal=principal,
            machine_id=doc.machine_id,
        )
        await db.commit()
        assert message.verified_at is not None
        doc_id = doc.doc_id

    async with AsyncSessionLocal() as db:
        hit = await qa_cache_service.lookup(
            db,
            factory_id=factory_id,
            question=question,
            principal=principal,
            machine_id=doc.machine_id,
        )
        assert hit is not None
        assert hit["cache_hit"] is True

        removed = await qa_cache_service.invalidate_by_doc_id(db, doc_id)
        assert removed >= 1
        await db.commit()

    async with AsyncSessionLocal() as db:
        miss = await qa_cache_service.lookup(
            db,
            factory_id=factory_id,
            question=question,
            principal=principal,
            machine_id=doc.machine_id,
        )
        assert miss is None
