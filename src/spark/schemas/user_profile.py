from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from spark.schemas.factories import FactoryBrief
from spark.schemas.job_positions import FactoryAccessEntry, JobPositionBrief


class UserProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: uuid.UUID
    username: str
    full_name: str | None = None
    email: str | None = None
    picture_url: str | None = None
    roles: list[str]
    factories: list[FactoryBrief]
    factory_access: list[FactoryAccessEntry]
    job_positions: list[JobPositionBrief]
    has_password: bool
    privacy_policy_accepted_at: datetime | None = None
    privacy_policy_version: str | None = None
    created_at: datetime
    is_super_admin: bool = False


class UserProfileUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=100)
    email: str | None = Field(default=None, min_length=3, max_length=120)
    job_position_id: uuid.UUID | None = None


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1)
    new_password: str = Field(min_length=8, max_length=128)
