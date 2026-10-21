"""External Postgres data sources (admin-configured live query)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Table, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from spark.core.database import Base

if TYPE_CHECKING:
    from spark.db.models.job_positions import JobPosition
    from spark.db.models.org import Factory

external_table_factories = Table(
    "external_table_factories",
    Base.metadata,
    Column("table_id", UUID(as_uuid=True), ForeignKey("external_data_source_tables.table_id", ondelete="CASCADE"), primary_key=True),
    Column("factory_id", String(20), ForeignKey("factories.factory_id", ondelete="CASCADE"), primary_key=True),
)

external_table_job_positions = Table(
    "external_table_job_positions",
    Base.metadata,
    Column("table_id", UUID(as_uuid=True), ForeignKey("external_data_source_tables.table_id", ondelete="CASCADE"), primary_key=True),
    Column("position_id", UUID(as_uuid=True), ForeignKey("job_positions.position_id", ondelete="CASCADE"), primary_key=True),
)


class ExternalDataSource(Base):
    __tablename__ = "external_data_sources"

    source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    factory_id: Mapped[str | None] = mapped_column(
        String(20),
        ForeignKey("factories.factory_id", ondelete="CASCADE"),
        nullable=True,
    )
    host: Mapped[str] = mapped_column(String(255), nullable=False)
    port: Mapped[int] = mapped_column(Integer, nullable=False, default=5432)
    database_name: Mapped[str] = mapped_column(String(128), nullable=False)
    username: Mapped[str] = mapped_column(String(128), nullable=False)
    password_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    ssl_mode: Mapped[str] = mapped_column(String(32), nullable=False, default="prefer")
    scope_column: Mapped[str | None] = mapped_column(String(128), nullable=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    allowed_tables: Mapped[list[ExternalDataSourceTable]] = relationship(
        "ExternalDataSourceTable",
        back_populates="source",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class ExternalDataSourceTable(Base):
    __tablename__ = "external_data_source_tables"

    table_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("external_data_sources.source_id", ondelete="CASCADE"),
        nullable=False,
    )
    schema_name: Mapped[str] = mapped_column(String(128), nullable=False, default="public")
    table_name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    columns_meta: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)

    source: Mapped[ExternalDataSource] = relationship("ExternalDataSource", back_populates="allowed_tables")

    # Empty = no extra restriction beyond the connection's own factory_id scope.
    factories: Mapped[list["Factory"]] = relationship(
        "Factory", secondary=external_table_factories, lazy="selectin"
    )
    job_positions: Mapped[list["JobPosition"]] = relationship(
        "JobPosition", secondary=external_table_job_positions, lazy="selectin"
    )
