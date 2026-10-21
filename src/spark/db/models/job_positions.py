from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from spark.core.database import Base


class JobPosition(Base):
    __tablename__ = "job_positions"

    position_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    position_code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    name_th: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user_links: Mapped[list["UserJobPosition"]] = relationship(
        back_populates="position", cascade="all, delete-orphan", lazy="select"
    )
    document_links: Mapped[list["DocumentJobPosition"]] = relationship(
        back_populates="position", cascade="all, delete-orphan", lazy="select"
    )


class UserJobPosition(Base):
    __tablename__ = "user_job_positions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="CASCADE"), primary_key=True
    )
    position_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("job_positions.position_id", ondelete="CASCADE"), primary_key=True
    )

    position: Mapped[JobPosition] = relationship(back_populates="user_links", lazy="select")


class DocumentJobPosition(Base):
    __tablename__ = "document_job_positions"

    doc_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.doc_id", ondelete="CASCADE"), primary_key=True
    )
    position_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("job_positions.position_id", ondelete="CASCADE"), primary_key=True
    )

    position: Mapped[JobPosition] = relationship(back_populates="document_links", lazy="select")
