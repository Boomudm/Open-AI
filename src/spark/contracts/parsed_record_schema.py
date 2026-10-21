"""Typed parser payload schema — validated at trust boundary."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

ChunkLevel = Literal["child", "parent", "table", "leaf", "diagram"]


class ParsedRecordPayload(BaseModel):
    """Parser-emitted fields before index enrichment (extra=forbid)."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    page_content: str | None = None
    page: int | None = None
    chunk_index: int | None = None
    page_count: int | None = None
    extraction_source: str | None = None
    chunk_level: ChunkLevel | None = None
    parent_chunk_id: str | None = None
    parent_content: str | None = None
    parent_index: int | None = None
    child_index_in_parent: int | None = None
    section_path: str | list[str] | None = None
    has_tables: bool | None = None
    parser_version: str | None = None
    block_type: str | None = None
    step_index: int | None = None
    chunk_id: str | None = None
    table_index: int | None = None
    table_headers: list[str] | None = None
    table_row_count: int | None = None
    part_numbers: list[str] | None = None
    section: str | None = None
    component_id: str | None = None
    machine_id: str | None = None
    source_sheet: str | None = None
    row_number: int | None = None
    json_key: str | None = None
    narrative: str | None = None
    ocr_page_count: int | None = None
    ocr_char_count: int | None = None
    ocr_confidence: float | None = None
    page_ocr_confidence: float | None = None
    ocr_rejected: bool | None = None
    needs_review: bool | None = None
    src_path: str | None = None
    tgt_path: str | None = None
    drawing_no: str | None = None
    extraction_confidence: str | None = None
    policy_quarantine: bool | None = Field(default=None, alias="_policy_quarantine")
    ocr_skipped: bool | None = Field(default=None, alias="_ocr_skipped")

    @field_validator("section_path", mode="before")
    @classmethod
    def _coerce_section_path(cls, value: Any) -> str | list[str] | None:
        if value is None:
            return None
        if isinstance(value, list):
            return [str(item) for item in value]
        return str(value)


def validate_parser_payload(raw: dict[str, Any]) -> dict[str, Any]:
    """Validate qdrant-route parser payload; return normalized dict."""
    validated = ParsedRecordPayload.model_validate(raw)
    return validated.model_dump(exclude_none=True, exclude_unset=True, by_alias=True)
