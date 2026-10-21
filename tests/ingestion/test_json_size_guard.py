"""JSON parser size guard tests (remediation v3 Phase 1)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from spark.ingestion.errors import PermanentIngestError
from spark.ingestion.parsers.json_parser import JSONParser, DEFAULT_MAX_JSON_DOCUMENT_BYTES


@pytest.mark.asyncio
async def test_json_rejects_oversized_document(tmp_path: Path) -> None:
    path = tmp_path / "big.json"
    payload = {"key": "x" * (DEFAULT_MAX_JSON_DOCUMENT_BYTES + 100)}
    path.write_text(json.dumps(payload), encoding="utf-8")

    parser = JSONParser()
    with pytest.raises(PermanentIngestError, match="JSON document exceeds"):
        async for _ in parser.parse(path, {}):
            pass


@pytest.mark.asyncio
async def test_json_splits_top_level_keys(tmp_path: Path) -> None:
    path = tmp_path / "multi.json"
    path.write_text(
        json.dumps({"part_a": {"id": 1}, "part_b": {"id": 2}}),
        encoding="utf-8",
    )

    parser = JSONParser()
    records = [rec async for rec in parser.parse(path, {"max_json_field_chars": 8192})]
    assert len(records) == 2
    keys = {rec.payload.get("json_key") for rec in records}
    assert keys == {"part_a", "part_b"}
