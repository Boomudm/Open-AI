"""RAG scope-broadening audit rows (Phase 10)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from spark.core.database import Base


class RagScopeBroadeningAudit(Base):
    __tablename__ = "rag_scope_broadening_audit"

    audit_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    factory_id: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    fallback_level: Mapped[int] = mapped_column(Integer, nullable=False)
    original_filter: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    broadened_filter: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
