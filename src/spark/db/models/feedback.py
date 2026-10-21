from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from spark.core.database import Base


class KnowledgeFeedback(Base):
    __tablename__ = "knowledge_feedback"

    feedback_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    factory_id: Mapped[str] = mapped_column(
        String(20), ForeignKey("factories.factory_id"), nullable=False, index=True
    )
    machine_id: Mapped[str | None] = mapped_column(
        String(20), ForeignKey("machines.machine_id"), nullable=True
    )
    source_type: Mapped[str] = mapped_column(String(30), nullable=False)
    doc_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.doc_id", ondelete="SET NULL"), index=True
    )
    page: Mapped[int | None] = mapped_column(Integer)
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chat_sessions.session_id", ondelete="SET NULL"),
    )
    message_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chat_messages.message_id", ondelete="SET NULL"),
        index=True,
    )
    comment: Mapped[str] = mapped_column(Text, nullable=False)
    issue_type: Mapped[str | None] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(20), default="open", index=True)
    context: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    resolution_note: Mapped[str | None] = mapped_column(Text)
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="SET NULL")
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    attachments: Mapped[list["KnowledgeFeedbackAttachment"]] = relationship(
        back_populates="feedback",
        cascade="all, delete-orphan",
        lazy="select",
        order_by="KnowledgeFeedbackAttachment.sort_order",
    )


class KnowledgeFeedbackAttachment(Base):
    __tablename__ = "knowledge_feedback_attachments"

    attachment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    feedback_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("knowledge_feedback.feedback_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    storage_uri: Mapped[str] = mapped_column(Text, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(127), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    feedback: Mapped[KnowledgeFeedback] = relationship(back_populates="attachments", lazy="select")
