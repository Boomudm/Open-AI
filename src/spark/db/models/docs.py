from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Computed,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from spark.core.database import Base


class Document(Base):
    """Single source of truth for every ingested document.

    Specialized per-type tables (drawings, certificates, inspections, incidents)
    are introduced in feat/p2-tables. Inventory tables in feat/p3-inventory.
    """

    __tablename__ = "documents"

    doc_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    factory_id: Mapped[str | None] = mapped_column(String(20), ForeignKey("factories.factory_id"))
    machine_id: Mapped[str | None] = mapped_column(
        String(20), ForeignKey("machines.machine_id"), index=True
    )
    component_id: Mapped[str | None] = mapped_column(String(30), ForeignKey("components.component_id"))

    document_category: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    document_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)

    title: Mapped[str | None] = mapped_column(String(500))
    language: Mapped[str] = mapped_column(String(10), default="th")
    revision: Mapped[str | None] = mapped_column(String(30))
    revision_sort_key: Mapped[int | None] = mapped_column(Integer, index=True)
    effective_date: Mapped[date | None] = mapped_column(Date)
    expiry_date: Mapped[date | None] = mapped_column(Date)

    source_file: Mapped[str] = mapped_column(String(500), nullable=False)
    original_filename: Mapped[str | None] = mapped_column(String(500))
    mime_type: Mapped[str | None] = mapped_column(String(127))
    storage_uri: Mapped[str | None] = mapped_column(String(1000))
    file_hash_sha256: Mapped[str | None] = mapped_column(String(64), index=True)
    file_size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    page_count: Mapped[int | None] = mapped_column(Integer)

    ingest_status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    chunks_count: Mapped[int] = mapped_column(Integer, default=0)
    active_ingest_generation: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    ingest_saga_state: Mapped[str | None] = mapped_column(String(30), index=True)
    quarantine_reason: Mapped[str | None] = mapped_column(Text)
    policy_scan_version: Mapped[str | None] = mapped_column(String(32))
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    released_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=True
    )
    content_risk_score: Mapped[float | None] = mapped_column()
    policy_findings_json: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    quarantine_artifact_uri: Mapped[str | None] = mapped_column(String(1000))
    sensitivity_level: Mapped[str | None] = mapped_column(String(20), index=True)
    retrieval_enabled: Mapped[bool] = mapped_column(default=True, index=True)

    extra_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.user_id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    chunks: Mapped[list["DocumentChunk"]] = relationship(
        back_populates="document", cascade="all, delete-orphan", lazy="select"
    )
    access_logs: Mapped[list["DocumentAccessLog"]] = relationship(
        back_populates="document", cascade="all, delete-orphan", lazy="select"
    )


class DocumentAccessLog(Base):
    __tablename__ = "document_access_log"

    log_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    doc_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.doc_id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True, index=True
    )
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    ip: Mapped[str | None] = mapped_column(String(45))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    document: Mapped[Document] = relationship(back_populates="access_logs", lazy="select")


class DocumentChunk(Base):
    """Mirror of Qdrant points — for cascade delete and chunk-level audit."""

    __tablename__ = "document_chunks"

    chunk_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    doc_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.doc_id", ondelete="CASCADE"), nullable=False, index=True
    )
    qdrant_point_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, unique=True)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    page: Mapped[int | None] = mapped_column(Integer)
    char_count: Mapped[int | None] = mapped_column(Integer)
    content: Mapped[str | None] = mapped_column(Text)
    content_tsv: Mapped[Any | None] = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('simple', coalesce(content, ''))", persisted=True),
        nullable=True,
    )
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    ingest_generation: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    parent_chunk_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    chunk_level: Mapped[str | None] = mapped_column(String(10), nullable=True)
    parent_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(32), nullable=True)
    embed_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    embed_model_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    chunk_schema_version: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    content_th_tokenized: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_tsv_th: Mapped[Any | None] = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('simple', coalesce(content_th_tokenized, ''))", persisted=True),
        nullable=True,
    )
    boost_tokens: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    sync_status: Mapped[str] = mapped_column(String(20), default="synced", nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    document: Mapped[Document] = relationship(back_populates="chunks", lazy="select")
