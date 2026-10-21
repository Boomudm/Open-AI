"""Structure-aware chunking: procedure steps and atomic table blocks."""

from __future__ import annotations

import re

from spark.ingestion.chunking.recursive import recursive_chunk_text

STEP_HEADING_RE = re.compile(
    r"(?m)^(?:"
    r"\d+\.\s+"  # 1. step
    r"|(?:ขั้นตอนที่|Step)\s*\d+"  # Thai / English procedure labels
    r")",
    re.IGNORECASE,
)
TABLE_BLOCK_RE = re.compile(r"(?ms)(### Tables\s*\n\n(?:\|[^\n]+\|\n)+)")


def split_structure_aware(text: str, *, chunk_size: int, chunk_overlap: int) -> list[str]:
    """Split on procedure steps and keep Markdown table blocks atomic."""
    if not text.strip():
        return []

    sections: list[str] = []
    last = 0
    for match in STEP_HEADING_RE.finditer(text):
        if match.start() > last:
            sections.append(text[last:match.start()].strip())
        last = match.start()
    if last < len(text):
        sections.append(text[last:].strip())
    if len(sections) <= 1:
        sections = [text.strip()]

    chunks: list[str] = []
    for section in sections:
        if not section:
            continue
        table_spans = list(TABLE_BLOCK_RE.finditer(section))
        if not table_spans:
            chunks.extend(recursive_chunk_text(section, chunk_size=chunk_size, chunk_overlap=chunk_overlap))
            continue
        cursor = 0
        for span in table_spans:
            before = section[cursor : span.start()].strip()
            if before:
                chunks.extend(
                    recursive_chunk_text(before, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
                )
            table_block = span.group(1).strip()
            if table_block:
                chunks.append(table_block)
            cursor = span.end()
        tail = section[cursor:].strip()
        if tail:
            chunks.extend(recursive_chunk_text(tail, chunk_size=chunk_size, chunk_overlap=chunk_overlap))

    return [c for c in chunks if c.strip()]


def split_table_atomic(text: str, *, chunk_size: int, chunk_overlap: int) -> list[str]:
    """Split narrative text but keep Markdown table blocks atomic."""
    if not text.strip():
        return []

    chunks: list[str] = []
    table_spans = list(TABLE_BLOCK_RE.finditer(text))
    if not table_spans:
        return recursive_chunk_text(text, chunk_size=chunk_size, chunk_overlap=chunk_overlap)

    cursor = 0
    for span in table_spans:
        before = text[cursor : span.start()].strip()
        if before:
            chunks.extend(recursive_chunk_text(before, chunk_size=chunk_size, chunk_overlap=chunk_overlap))
        table_block = span.group(1).strip()
        if table_block:
            chunks.append(table_block)
        cursor = span.end()
    tail = text[cursor:].strip()
    if tail:
        chunks.extend(recursive_chunk_text(tail, chunk_size=chunk_size, chunk_overlap=chunk_overlap))
    return [c for c in chunks if c.strip()]
