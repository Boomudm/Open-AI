"""Typed Qdrant ingest payload schema — validated at index write."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, field_validator

ChunkLevel = Literal["child", "parent", "table", "leaf", "diagram"]


class QdrantPayloadSchema(BaseModel):
    """Canonical Qdrant point payload written by qdrant_writer."""

    model_config = ConfigDict(extra="forbid")

    doc_id: str
    chunk_id: str
    chunk_index: int = 0
    page: int | None = None
    source_sheet: str | None = None
    row_number: int | None = None
    extraction_source: str | None = None
    factory_id: str | None = None
    machine_id: str | None = None
    component_id: str | None = None
    document_category: str | None = None
    document_type: str | None = None
    language: str | None = None
    revision: str | None = None
    revision_sort_key: int | None = None
    source_file: str | None = None
    title: str | None = None
    effective_date: int | None = None
    expiry_date: int | None = None
    ingested_at: int
    ingest_version: str
    ingest_generation: int
    embed_model_id: str
    embed_model: str
    embed_model_version: str
    embed_provider: str
    embed_dimension: int
    config_hash: str
    content_hash: str
    chunk_schema_version: int
    sparse_encoder_id: str
    page_content: str
    parent_chunk_id: str | None = None
    parent_index: int | None = None
    child_index_in_parent: int | None = None
    chunk_level: ChunkLevel | None = None
    has_tables: bool | None = None
    extraction_confidence: str | None = None
    section_path: str | list[str] | None = None
    retrieval_enabled: bool = True
    boost_tokens: list[str] | None = None
    # Access-control — list of position UUIDs that may retrieve this chunk.
    # Absent (None) means no position restriction.
    restricted_position_ids: list[str] | None = None
    drawing_no: str | None = None
    sensitivity_level: str | None = None
    needs_review: bool | None = None
    # Exact PLC/IO-mapping symlink tag paths (e.g. "RES0.BELT_CALIB_SENSOR") —
    # enables deterministic exact-match filtering instead of relying purely on
    # embedding/lexical rerank across hundreds of structurally-similar rows.
    src_path: str | None = None
    tgt_path: str | None = None

    @field_validator("section_path", mode="before")
    @classmethod
    def _coerce_section_path(cls, value: Any) -> str | list[str] | None:
        if value is None:
            return None
        if isinstance(value, list):
            return [str(item) for item in value]
        return str(value)


def validate_qdrant_payload(raw: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize Qdrant payload; drops None values."""
    validated = QdrantPayloadSchema.model_validate(raw)
    return {k: v for k, v in validated.model_dump().items() if v is not None}
