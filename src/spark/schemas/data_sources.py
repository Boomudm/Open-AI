"""Pydantic schemas for external data source admin API."""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, Field


class ExternalColumnMeta(BaseModel):
    column_name: str
    data_type: str | None = None
    is_nullable: str | None = None


class ExternalTableAllowlistItem(BaseModel):
    schema_name: str = "public"
    table_name: str
    description: str | None = None
    columns_meta: list[ExternalColumnMeta] = Field(default_factory=list)
    # Empty = no extra restriction beyond the connection's own factory_id scope.
    factory_ids: list[str] = Field(default_factory=list)
    position_ids: list[uuid.UUID] = Field(default_factory=list)


class ExternalTableAllowlistUpdate(BaseModel):
    tables: list[ExternalTableAllowlistItem]


class ExternalDataSourceCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    description: str | None = None
    factory_id: str | None = None
    host: str = Field(..., min_length=1, max_length=255)
    port: int = Field(5432, ge=1, le=65535)
    database_name: str = Field(..., min_length=1, max_length=128)
    username: str = Field(..., min_length=1, max_length=128)
    password: str = Field(..., min_length=1)
    ssl_mode: str = Field("prefer", max_length=32)
    scope_column: str | None = Field(None, max_length=128)
    is_enabled: bool = False


class ExternalDataSourceUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=128)
    description: str | None = None
    factory_id: str | None = None
    host: str | None = Field(None, min_length=1, max_length=255)
    port: int | None = Field(None, ge=1, le=65535)
    database_name: str | None = Field(None, min_length=1, max_length=128)
    username: str | None = Field(None, min_length=1, max_length=128)
    password: str | None = Field(None, min_length=1)
    ssl_mode: str | None = Field(None, max_length=32)
    scope_column: str | None = Field(None, max_length=128)
    is_enabled: bool | None = None


class ExternalTableOut(BaseModel):
    table_id: uuid.UUID
    schema_name: str
    table_name: str
    description: str | None = None
    columns_meta: list[dict[str, Any]] = Field(default_factory=list)
    factory_ids: list[str] = Field(default_factory=list)
    position_ids: list[uuid.UUID] = Field(default_factory=list)


class ExternalDataSourceOut(BaseModel):
    source_id: uuid.UUID
    name: str
    description: str | None = None
    factory_id: str | None = None
    host: str
    port: int
    database_name: str
    username: str
    ssl_mode: str
    scope_column: str | None = None
    is_enabled: bool
    allowed_tables: list[ExternalTableOut] = Field(default_factory=list)


class ExternalConnectionTestResult(BaseModel):
    ok: bool
    message: str


class ExternalConnectionTestRequest(BaseModel):
    """Raw connection params for testing before a data source is saved."""

    host: str = Field(..., min_length=1, max_length=255)
    port: int = Field(5432, ge=1, le=65535)
    database_name: str = Field(..., min_length=1, max_length=128)
    username: str = Field(..., min_length=1, max_length=128)
    password: str = Field(..., min_length=1)
    ssl_mode: str = Field("prefer", max_length=32)


class ExternalDiscoveredTable(BaseModel):
    schema_name: str
    table_name: str
    columns: list[ExternalColumnMeta]
