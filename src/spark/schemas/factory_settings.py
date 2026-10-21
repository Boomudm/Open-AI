"""Per-factory settings schemas for admin API."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class FactoryRagSettingsPatch(BaseModel):
    min_max_score: float | None = Field(None, ge=0.0, le=1.0)
    top_k_default: int | None = Field(None, ge=1, le=20)
    chunk_profile: str | None = Field(None, max_length=64)


class FactoryIngestSettingsPatch(BaseModel):
    backend: Literal["native"] | None = None
    chunking_strategy: Literal["recursive", "semantic"] | None = None
    chunking_profile: str | None = Field(None, max_length=64)
    embedding_profile: str | None = Field(None, max_length=64)


class NotificationChannelPatch(BaseModel):
    type: Literal["webhook", "smtp", "line"]
    url: str | None = None
    host: str | None = None
    port: int | None = Field(None, ge=1, le=65535)
    username: str | None = None
    password: str | None = None
    from_addr: str | None = Field(None, alias="from")
    token: str | None = None

    model_config = {"populate_by_name": True}


class FactoryNotificationsPatch(BaseModel):
    enabled: bool | None = None
    channels: list[NotificationChannelPatch] | None = None
    insights_hotness: bool | None = None
    ingest_failed: bool | None = None


class FactoryFeaturesPatch(BaseModel):
    """Per-factory profile overrides — security gates cannot be disabled."""

    ingest_policy_enabled: bool | None = None
    rag_circuit_enabled: bool | None = None
    lexical_engine: Literal["postgres_thai_v3"] | None = None
    query_rewrite_enabled: bool | None = None
    extractive_first_enabled: bool | None = None
    extractive_first_for_safety_types: bool | None = None
    sparse_vectors_enabled: bool | None = None

    @field_validator(
        "ingest_policy_enabled",
        "rag_circuit_enabled",
        "query_rewrite_enabled",
        "sparse_vectors_enabled",
    )
    @classmethod
    def security_flags_cannot_disable(cls, value: bool | None) -> bool | None:
        if value is False:
            raise ValueError("security-related feature flags cannot be disabled via factory settings")
        return value

    @field_validator("extractive_first_enabled", "extractive_first_for_safety_types")
    @classmethod
    def extractive_first_flags_are_retired(cls, value: bool | None) -> bool | None:
        if value is not None:
            raise ValueError("extractive-first generation has been retired")
        return value


class FactorySettingsPatch(BaseModel):
    rag: FactoryRagSettingsPatch | None = None
    ingest: FactoryIngestSettingsPatch | None = None
    notifications: FactoryNotificationsPatch | None = None
    timezone: str | None = Field(None, max_length=64)
    llm_profile: str | None = Field(None, max_length=32)
    features: FactoryFeaturesPatch | None = None

    @field_validator("timezone")
    @classmethod
    def timezone_non_empty(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("timezone must not be empty")
        return value


class FactorySettingsResponse(BaseModel):
    factory_id: str
    effective: dict[str, Any]
    stored: dict[str, Any]
