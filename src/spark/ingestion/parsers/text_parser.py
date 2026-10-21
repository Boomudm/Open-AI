from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pandas as pd

from spark.ingestion.chunk.registry import chunk_text
from spark.ingestion.config_resolver import get_chunking_config
from spark.ingestion.parsers.base import ParsedRecord, ParserError, ParserPlugin


def _read_text_file(file_path: Path) -> str:
    last_error: Exception | None = None
    for encoding in ("utf-8-sig", "utf-8", "cp874", "latin-1"):
        try:
            return file_path.read_text(encoding=encoding)
        except UnicodeDecodeError as exc:
            last_error = exc
            continue
    raise ParserError(
        "text_decode_failed",
        f"Could not decode text file with supported encodings: {last_error}",
    )


def _read_csv(file_path: Path) -> pd.DataFrame:
    return pd.read_csv(file_path, dtype=str, keep_default_na=False)


def _row_text(sheet_name: str, row_number: int, row: dict[str, Any]) -> str:
    parts = [f"Sheet: {sheet_name}", f"Row: {row_number}"]
    for key, value in row.items():
        text = str(value or "").strip()
        if text:
            parts.append(f"{key}: {text}")
    return "\n".join(parts)


class TextParser(ParserPlugin):
    name = "text"
    supported_extensions = (".txt", ".md", ".csv")

    async def parse(self, file_path: Path, config: dict[str, Any]) -> AsyncIterator[ParsedRecord]:
        chunking = get_chunking_config(config)
        chunk_size = chunking.get("chunk_size", 1000)
        chunk_overlap = chunking.get("chunk_overlap", 150)
        strategy = chunking.get("strategy")
        default_route = config.get("default_route", "qdrant") if isinstance(config, dict) else config.default_route

        if file_path.suffix.lower() == ".csv":
            async for record in self._parse_csv(
                file_path,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                strategy=strategy,
                default_route=default_route,
            ):
                yield record
            return

        text = await asyncio.get_running_loop().run_in_executor(
            None, _read_text_file, file_path
        )
        chunks = chunk_text(text, chunk_size=chunk_size, chunk_overlap=chunk_overlap, strategy=strategy)
        if not chunks:
            raise ParserError("empty_text", "Text file produced no chunks")

        for idx, chunk in enumerate(chunks):
            yield ParsedRecord(
                route=default_route,
                payload={
                    "page_content": chunk,
                    "chunk_index": idx,
                    "page": None,
                    "extraction_source": "text",
                },
                text_for_embedding=chunk,
                source_locator={"chunk_index": idx},
            )

    async def _parse_csv(
        self,
        file_path: Path,
        *,
        chunk_size: int,
        chunk_overlap: int,
        strategy: str | None,
        default_route: str,
    ) -> AsyncIterator[ParsedRecord]:
        df = await asyncio.get_running_loop().run_in_executor(None, _read_csv, file_path)
        if df is None or df.empty:
            raise ParserError("empty_csv", "CSV file produced no rows")

        chunk_index = 0
        sheet_name = "CSV"
        for row_num, raw in df.iterrows():
            row = {k: (None if pd.isna(v) else str(v).strip()) for k, v in raw.items()}
            row_number = int(row_num) + 2
            text = _row_text(sheet_name, row_number, row)
            if not text.strip():
                continue
            for chunk in chunk_text(text, chunk_size=chunk_size, chunk_overlap=chunk_overlap, strategy=strategy):
                yield ParsedRecord(
                    route=default_route,
                    payload={
                        "page_content": chunk,
                        "source_sheet": sheet_name,
                        "row_number": row_number,
                        "chunk_index": chunk_index,
                        "page": None,
                        "extraction_source": "csv",
                    },
                    text_for_embedding=chunk,
                    source_locator={"sheet": sheet_name, "row": row_number},
                )
                chunk_index += 1
