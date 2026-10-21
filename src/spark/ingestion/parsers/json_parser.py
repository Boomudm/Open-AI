from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from spark.core.logging import get_logger
from spark.ingestion.chunk.registry import PARSER_VERSION
from spark.ingestion.errors import PermanentIngestError
from spark.ingestion.parsers.base import ParsedRecord, ParserError, ParserPlugin

PARSER_VERSION_JSON = PARSER_VERSION

log = get_logger(__name__)

DEFAULT_MAX_JSON_FIELD_CHARS = 8192
DEFAULT_MAX_JSON_DOCUMENT_BYTES = 1_048_576


def _load_json(path: Path) -> Any:
    raw = path.read_bytes()
    if len(raw) > DEFAULT_MAX_JSON_DOCUMENT_BYTES:
        raise PermanentIngestError(
            "json_size_exceeded",
            f"JSON document exceeds {DEFAULT_MAX_JSON_DOCUMENT_BYTES} bytes",
        )
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _render_diagram(data: dict[str, Any]) -> list[ParsedRecord]:
    machine_id = data.get("machine_id")
    machine_name = data.get("machine_name", "")
    records: list[ParsedRecord] = []
    parts = data.get("parts") or []
    for idx, part in enumerate(parts):
        lines = [
            f"เครื่อง {machine_id} ({machine_name}) ชิ้นส่วน {part.get('part_name', '')}",
            f"รหัส: {part.get('part_code', '')}",
            f"หมวด: {part.get('category', '')}",
        ]
        for anomaly in part.get("common_anomalies", []) or []:
            lines.append(
                f"อาการ: {anomaly.get('symptom', '')} "
                f"สาเหตุ: {', '.join(anomaly.get('possible_causes', []))} "
                f"แก้ไข: {', '.join(anomaly.get('recommended_actions', []))} "
                f"ระดับ: {anomaly.get('severity', '')}"
            )
        text = "\n".join(lines)
        records.append(
            ParsedRecord(
                route="qdrant",
                payload={
                    "page_content": text,
                    "chunk_index": idx,
                    "page": None,
                    "component_id": part.get("part_id"),
                    "parser_version": PARSER_VERSION_JSON,
                },
                text_for_embedding=text,
                source_locator={"part_id": part.get("part_id")},
            )
        )
    return records


def _render_generic_object(
    data: Any,
    *,
    max_field_chars: int,
) -> list[ParsedRecord]:
    if not isinstance(data, dict):
        text = json.dumps(data, ensure_ascii=False, indent=2)
        if len(text.encode("utf-8")) > DEFAULT_MAX_JSON_DOCUMENT_BYTES:
            raise PermanentIngestError("json_size_exceeded", "serialized JSON exceeds size cap")
        return [
            ParsedRecord(
                route="qdrant",
                payload={
                    "page_content": text[:max_field_chars],
                    "chunk_index": 0,
                    "page": None,
                    "parser_version": PARSER_VERSION_JSON,
                },
                text_for_embedding=text[:max_field_chars],
                source_locator={},
            )
        ]

    records: list[ParsedRecord] = []
    for idx, (key, value) in enumerate(data.items()):
        text = json.dumps({key: value}, ensure_ascii=False, indent=2)
        if len(text) > max_field_chars:
            text = text[: max_field_chars - 3] + "..."
        records.append(
            ParsedRecord(
                route="qdrant",
                payload={
                    "page_content": text,
                    "chunk_index": idx,
                    "page": None,
                    "json_key": key,
                    "parser_version": PARSER_VERSION_JSON,
                },
                text_for_embedding=text,
                source_locator={"json_key": key},
            )
        )
    return records


class JSONParser(ParserPlugin):
    name = "json"
    supported_extensions = (".json",)

    async def parse(self, file_path: Path, config: dict[str, Any]) -> AsyncIterator[ParsedRecord]:
        max_field_chars = int(
            config.get("max_json_field_chars", DEFAULT_MAX_JSON_FIELD_CHARS)
            or DEFAULT_MAX_JSON_FIELD_CHARS
        )
        try:
            data = await asyncio.get_running_loop().run_in_executor(None, _load_json, file_path)
        except PermanentIngestError:
            raise
        except Exception as exc:
            raise ParserError("parser_failed", f"cannot read JSON: {exc}") from exc

        if isinstance(data, dict) and "parts" in data and "machine_id" in data:
            for rec in _render_diagram(data):
                yield rec
            log.info("json_parse_diagram_complete", file=str(file_path))
            return

        records = _render_generic_object(data, max_field_chars=max_field_chars)
        for rec in records:
            yield rec
        log.info("json_parse_generic_complete", file=str(file_path), records=len(records))
