from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class FactoryBrief(BaseModel):
    factory_id: str
    factory_name: str


class FactoryAdmin(BaseModel):
    factory_id: str
    factory_name: str
    location: str | None = None
    created_at: datetime | None = None


class FactoryCreate(BaseModel):
    factory_id: str = Field(min_length=2, max_length=20, examples=["F-03"])
    factory_name: str = Field(min_length=1, max_length=100, examples=["Rayong Plant"])
    location: str | None = Field(None, max_length=200, examples=["Rayong"])
