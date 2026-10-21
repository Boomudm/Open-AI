from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, Field


class JobPositionBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    position_id: uuid.UUID
    position_code: str
    name_th: str
    description: str | None = None


class JobPositionAdmin(JobPositionBrief):
    is_active: bool = True
    sort_order: int = 0
    document_count: int = 0
    user_count: int = 0


class JobPositionCreate(BaseModel):
    position_code: str = Field(min_length=2, max_length=50)
    name_th: str = Field(min_length=2, max_length=200)
    description: str | None = None
    sort_order: int = 0


class JobPositionUpdate(BaseModel):
    name_th: str | None = Field(default=None, min_length=2, max_length=200)
    description: str | None = None
    is_active: bool | None = None
    sort_order: int | None = None


class JobPositionUsage(BaseModel):
    position_id: uuid.UUID
    document_count: int
    user_count: int


class FactoryAccessEntry(BaseModel):
    factory_id: str
    access_level: str


class AdminUserBrief(BaseModel):
    user_id: uuid.UUID
    username: str
    full_name: str | None = None
    email: str | None = None
    is_active: bool
    roles: list[str]
    factory_access: list[FactoryAccessEntry]
    job_position_ids: list[uuid.UUID]
    token_version: int
    is_super_admin: bool = False


class AdminUserUpdate(BaseModel):
    role: str | None = Field(default=None, description="employee, operator, or admin")
    is_active: bool | None = None
    is_super_admin: bool | None = None
    factory_access: list[FactoryAccessEntry] | None = None
    job_position_ids: list[uuid.UUID] | None = None


class AdminUserCreate(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    full_name: str | None = Field(default=None, max_length=200)
    username: str | None = Field(default=None, min_length=2, max_length=50)
    password: str = Field(min_length=8, max_length=128)
    role: str = Field(default="employee", description="employee, operator, or admin")
    factory_access: list[FactoryAccessEntry] = Field(default_factory=list)
    job_position_ids: list[uuid.UUID] = Field(default_factory=list)
