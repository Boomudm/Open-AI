from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pandas as pd

from spark.core.logging import get_logger
from spark.ingestion.chunk.registry import chunk_text
from spark.ingestion.config_resolver import get_chunking_config
from spark.ingestion.parsers.base import ParsedRecord, ParserPlugin

log = get_logger(__name__)


def _normalize_header(header: Any) -> str:
    return str(header).strip().lower() if header is not None else ""


def _build_column_index(
    columns: list[str], column_map: dict[str, list[str]]
) -> dict[str, str]:
    """Return mapping of canonical_field -> actual_column_name (None if not found)."""
    norm_to_actual = {_normalize_header(c): c for c in columns}
    resolved: dict[str, str] = {}
    for canonical, candidates in column_map.items():
        for cand in candidates:
            cand_norm = _normalize_header(cand)
            if cand_norm in norm_to_actual:
                resolved[canonical] = norm_to_actual[cand_norm]
                break
    return resolved


def _build_column_index_by_position(
    columns: list[str], column_map_by_index: dict[str, int]
) -> dict[str, str]:
    """Map canonical fields to column names by zero-based index (bilateral Excel sheets)."""
    resolved: dict[str, str] = {}
    for canonical, index in column_map_by_index.items():
        try:
            idx = int(index)
        except (TypeError, ValueError):
            continue
        if 0 <= idx < len(columns):
            resolved[canonical] = columns[idx]
    return resolved


def _passes_sheet_filter(columns: list[str], selector: dict[str, Any]) -> bool:
    if not selector:
        return True
    norm = {_normalize_header(c) for c in columns}
    headers_any_of = selector.get("required_headers_any_of") or []
    if not headers_any_of:
        return True
    for header_group in headers_any_of:
        if all(_normalize_header(h) in norm for h in header_group):
            return True
    return False


def _read_excel_sheets(file_path: Path, header_row: int = 0) -> dict[str, pd.DataFrame]:
    if file_path.suffix.lower() == ".csv":
        return {"CSV": pd.read_csv(file_path, dtype=str, keep_default_na=False, header=header_row)}
    return pd.read_excel(file_path, sheet_name=None, dtype=str, header=header_row)


def _generic_row_text(sheet_name: str, row_number: int, row: dict[str, Any]) -> str:
    parts: list[str] = [f"Sheet: {sheet_name}", f"Row: {row_number}"]
    for key, value in row.items():
        if value is None:
            continue
        text = str(value).strip()
        if not text:
            continue
        parts.append(f"{key}: {text}")
    return "\n".join(parts)


class ExcelParser(ParserPlugin):
    name = "excel"
    supported_extensions = (".xlsx", ".xls", ".csv")

    async def parse(self, file_path: Path, config: dict[str, Any]) -> AsyncIterator[ParsedRecord]:
        header_row = int(config.get("header_row", 0) or 0)
        sheets = await asyncio.get_running_loop().run_in_executor(
            None, _read_excel_sheets, file_path, header_row
        )
        column_map: dict[str, list[str]] = config.get("column_map") or {}
        column_map_by_index: dict[str, int] = config.get("column_map_by_index") or {}
        sheet_selector: dict[str, Any] = config.get("sheet_selector") or {}
        narrative_tpl: str | None = config.get("narrative_template")
        default_route = config.get("default_route", "both")
        chunking = get_chunking_config(config)
        chunk_size = chunking.get("chunk_size", 1000)
        chunk_overlap = chunking.get("chunk_overlap", 150)
        generic_chunk_index = 0

        for sheet_name, df in sheets.items():
            if df is None or df.empty:
                continue
            cols = list(df.columns)
            if not _passes_sheet_filter(cols, sheet_selector):
                log.debug("excel_skip_sheet", sheet=sheet_name)
                continue

            resolved = (
                _build_column_index_by_position(cols, column_map_by_index)
                if column_map_by_index
                else _build_column_index(cols, column_map)
            )

            for row_num, raw in df.iterrows():
                row_dict = {k: (None if pd.isna(v) else str(v).strip()) for k, v in raw.items()}
                # 1-based spreadsheet row: rows skipped above the header
                # (header_row) + the header row itself + 1-based offset.
                # Cited row numbers must match what the user sees in Excel.
                row_number = int(row_num) + header_row + 2

                if not column_map and not column_map_by_index:
                    text = _generic_row_text(sheet_name, row_number, row_dict)
                    if not text.strip():
                        continue
                    for chunk in chunk_text(text, chunk_size=chunk_size, chunk_overlap=chunk_overlap):
                        yield ParsedRecord(
                            route=default_route,
                            payload={
                                "page_content": chunk,
                                "source_sheet": sheet_name,
                                "row_number": row_number,
                                "chunk_index": generic_chunk_index,
                                "page": None,
                            },
                            text_for_embedding=chunk,
                            source_locator={"sheet": sheet_name, "row": row_number},
                        )
                        generic_chunk_index += 1
                    continue

                field_values: dict[str, Any] = {}
                for canonical, actual_col in resolved.items():
                    field_values[canonical] = row_dict.get(actual_col)

                # Skip rows with no mapped content at all (spacer/title rows) —
                # they would otherwise index as empty or comment-only chunks.
                if not any(str(v or "").strip() for v in field_values.values()):
                    continue
                if not (field_values.get("src_path") or field_values.get("page_content")):
                    # Skip title rows / empty symlink rows
                    if column_map_by_index and not any(
                        str(field_values.get(k) or "").strip()
                        for k in ("src_path", "tgt_path", "src_device")
                    ):
                        continue

                target_table = (config.get("postgres") or {}).get("table")
                # Qdrant-route payloads are validated against a fixed schema
                # (extra=forbid) — arbitrary column_map_by_index canonical
                # fields (src_device, tgt_type, ...) have no defined home
                # there and no Qdrant consumer once rendered into the
                # narrative below. Only carry them through when a structured
                # Postgres mirror table is actually configured to receive them.
                payload: dict[str, Any] = dict(field_values) if target_table else {}

                # src_path/tgt_path ARE first-class Qdrant payload fields (see
                # QdrantPayloadSchema) regardless of target_table — they let
                # retrieval do a deterministic exact-match lookup on PLC/IO
                # symlink tags instead of relying purely on embedding/lexical
                # rerank across many structurally-similar rows.
                for exact_key in ("src_path", "tgt_path"):
                    exact_value = field_values.get(exact_key)
                    if exact_value:
                        payload[exact_key] = exact_value

                if narrative_tpl:
                    if "tgt_path" in field_values:
                        field_values["target_clause"] = (
                            " connects to {tgt_device} ({tgt_type}, {tgt_direction}) at {tgt_path}".format_map(
                                {k: field_values.get(k) or "?" for k in ("tgt_device", "tgt_type", "tgt_direction", "tgt_path")}
                            )
                            if field_values.get("tgt_path")
                            else " (no mapped target in this sheet)"
                        )
                    if "comment" in field_values:
                        field_values["comment_clause"] = (
                            f" {field_values['comment'].strip()}" if str(field_values.get("comment") or "").strip() else ""
                        )
                    effective_tpl = narrative_tpl
                    if not str(field_values.get("src_path") or "").strip() and str(
                        field_values.get("tgt_path") or ""
                    ).strip():
                        # One-sided row: only the hardware-port half is filled.
                        # Rendering the main template would produce a false
                        # statement — "(, ) at  connects to X" reads as if
                        # something connects to that port. Bilateral symlink
                        # sheets have hundreds of these rows.
                        effective_tpl = config.get("narrative_template_tgt_only") or (
                            "No symbolic link mapped in this row. Hardware port:"
                            " {tgt_device} ({tgt_type}, {tgt_direction}) at {tgt_path}.{comment_clause}"
                        )
                    payload["narrative"] = _safe_format(effective_tpl, field_values)
                    payload["page_content"] = payload["narrative"]

                payload["source_sheet"] = sheet_name
                payload["row_number"] = row_number

                embed_text = payload.get("narrative") or payload.get("page_content")
                if not str(embed_text or "").strip() and not target_table:
                    # Nothing to embed and no structured mirror table to feed —
                    # indexing this row would create an empty-content vector.
                    log.warning(
                        "excel_row_skipped_no_content", sheet=sheet_name, row=row_number
                    )
                    continue
                yield ParsedRecord(
                    route=default_route,
                    payload=payload,
                    text_for_embedding=embed_text,
                    target_table=target_table,
                    source_locator={"sheet": sheet_name, "row": payload["row_number"]},
                )


def _safe_format(template: str, data: dict[str, Any]) -> str:
    class _SafeDict(dict):
        def __missing__(self, key):  # type: ignore[override]
            return ""

    try:
        # support {component_part} optional clauses
        composed = {k: ("" if v is None else v) for k, v in data.items()}
        composed.setdefault(
            "component_part",
            f" / {data['component_id']}" if data.get("component_id") else "",
        )
        return template.format_map(_SafeDict(composed)).strip()
    except Exception:
        return ""
