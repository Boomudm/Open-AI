"""Contract tests for typed parser payload schema."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from spark.contracts.parsed_record_schema import ParsedRecordPayload, validate_parser_payload
from spark.ingestion.parsers.base import ParsedRecord


def test_unknown_parser_payload_key_rejected() -> None:
    with pytest.raises(ValidationError):
        ParsedRecordPayload.model_validate({"page_content": "hello", "unexpected": True})


def test_valid_parser_payload_normalizes() -> None:
    payload = validate_parser_payload(
        {
            "page_content": "bearing torque 12 Nm",
            "page": 1,
            "chunk_level": "child",
            "parent_chunk_id": "parent-1",
            "parent_content": "full parent body",
        }
    )
    assert payload["page_content"] == "bearing torque 12 Nm"
    assert payload["parent_chunk_id"] == "parent-1"


def test_parsed_record_validates_qdrant_route_on_init() -> None:
    record = ParsedRecord(
        route="qdrant",
        payload={"page_content": "text", "chunk_index": 0},
        text_for_embedding="text",
    )
    assert record.payload["page_content"] == "text"


def test_parsed_record_rejects_unknown_key_at_init() -> None:
    with pytest.raises(ValidationError):
        ParsedRecord(
            route="qdrant",
            payload={"page_content": "text", "evil_key": "drop-me"},
            text_for_embedding="text",
        )


def test_postgres_route_skips_parser_schema_validation() -> None:
    record = ParsedRecord(
        route="postgres",
        payload={"part_no": "P-1", "custom_column": "value"},
        text_for_embedding="",
    )
    assert record.payload["custom_column"] == "value"
