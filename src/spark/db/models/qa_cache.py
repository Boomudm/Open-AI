from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from spark.core.database import Base


class VerifiedQACache(Base):
    __tablename__ = "verified_qa_cache"

    cache_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    factory_id: Mapped[str] = mapped_column(
        String(20), ForeignKey("factories.factory_id"), nullable=False, index=True
    )
    machine_id: Mapped[str | None] = mapped_column(
        String(20), ForeignKey("machines.machine_id"), nullable=True, index=True
    )
    intent: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    question_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    filter_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    question_embedding: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    answer_text: Mapped[str] = mapped_column(Text, nullable=False)
    sources: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    source_doc_ids: Mapped[list] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, server_default="{}"
    )
    verification_method: Mapped[str | None] = mapped_column(String(40), nullable=True)
    verification_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_message_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chat_messages.message_id", ondelete="SET NULL"),
        nullable=True,
    )
    hit_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
