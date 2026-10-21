from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from spark.schemas.openapi_examples import ALIAS_CREATE, MACHINE_CREATE, MACHINE_MC001


class MachineCreate(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [MACHINE_CREATE]})
    machine_id: str = Field(min_length=3, max_length=20)
    factory_id: str = Field(min_length=1, max_length=20)
    machine_name: str = Field(min_length=1, max_length=100)
    machine_type: str | None = None
    manufacturer: str | None = None
    model_number: str | None = None
    install_date: date | None = None
    notes: str | None = None


class MachinePatch(BaseModel):
    machine_name: str | None = None
    machine_type: str | None = None
    manufacturer: str | None = None
    model_number: str | None = None
    install_date: date | None = None
    notes: str | None = None
    is_active: bool | None = None


class MachineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, json_schema_extra={"examples": [MACHINE_MC001]})

    machine_id: str
    factory_id: str
    machine_name: str
    machine_type: str | None
    manufacturer: str | None
    model_number: str | None
    install_date: date | None
    is_active: bool
    notes: str | None
    image_updated_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class AliasCreate(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [ALIAS_CREATE]})

    alias: str = Field(min_length=1, max_length=100, examples=["เครื่อง 1"])
    source: str | None = "manual"


class AliasOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    machine_id: str
    alias: str
    source: str | None
