"""SOP / procedure step boundary chunking — LOTO, safety blocks, numbered steps."""

from __future__ import annotations

import re
from dataclasses import dataclass

from spark.ingestion.chunk.section_path import section_path_for_chunk
from spark.ingestion.chunk.types import ChunkLeaf
from spark.ingestion.chunking.recursive import recursive_chunk_text

_LOTO_RE = re.compile(
    r"(?i)^(?:LOTO|LOCK\s*OUT|TAG\s*OUT|Lock-?Out.?Tag-?Out)\b"
)
_WARNING_RE = re.compile(
    r"(?i)^(?:WARNING|CAUTION|DANGER|NOTICE|คำเตือน|ระวัง|อันตราย)\b"
)
_STEP_RE = re.compile(
    r"(?m)^(?:"
    r"(?:\d+|[\u0E50-\u0E59]+)\.\s+"
    r"|(?:Step|ขั้นตอนที่|ขั้นที่)\s*[\d\u0E50-\u0E59]+[\s.:：-]*"
    r")"
)


@dataclass(frozen=True)
class SopSegment:
    text: str
    block_type: str
    step_index: int | None = None


def _warning_block_type(line: str) -> str:
    upper = line.upper()
    if "CAUTION" in upper or "ระวัง" in line:
        return "caution"
    return "warning"


def split_sop_segments(text: str) -> list[SopSegment]:
    """Split procedure text into atomic LOTO / safety / step segments."""
    if not text.strip():
        return []

    lines = text.splitlines()
    segments: list[SopSegment] = []
    buf: list[str] = []
    buf_type = "preamble"
    step_index: int | None = None
    index = 0

    def flush() -> None:
        nonlocal buf, buf_type, step_index
        body = "\n".join(buf).strip()
        if body:
            segments.append(
                SopSegment(
                    text=body,
                    block_type=buf_type,
                    step_index=step_index if buf_type == "sop_step" else None,
                )
            )
        buf = []
        buf_type = "preamble"
        step_index = None

    while index < len(lines):
        line = lines[index]
        stripped = line.strip()

        if not stripped:
            if buf:
                buf.append(line)
            index += 1
            continue

        if _LOTO_RE.match(stripped):
            flush()
            buf_type = "loto"
            buf = [line]
            index += 1
            while index < len(lines):
                nxt = lines[index].strip()
                if not nxt:
                    break
                if _STEP_RE.match(nxt) or _WARNING_RE.match(nxt) or _LOTO_RE.match(nxt):
                    break
                buf.append(lines[index])
                index += 1
            flush()
            continue

        if _WARNING_RE.match(stripped):
            flush()
            buf_type = _warning_block_type(stripped)
            buf = [line]
            index += 1
            while index < len(lines):
                nxt = lines[index].strip()
                if not nxt:
                    break
                if _STEP_RE.match(nxt) or _LOTO_RE.match(nxt) or _WARNING_RE.match(nxt):
                    break
                buf.append(lines[index])
                index += 1
            flush()
            continue

        if _STEP_RE.match(stripped):
            flush()
            step_index = sum(1 for seg in segments if seg.block_type == "sop_step") + 1
            buf_type = "sop_step"
            buf = [line]
            index += 1
            while index < len(lines):
                nxt = lines[index].strip()
                if not nxt:
                    break
                if _STEP_RE.match(nxt) or _LOTO_RE.match(nxt) or _WARNING_RE.match(nxt):
                    break
                buf.append(lines[index])
                index += 1
            flush()
            continue

        if buf_type == "preamble" and not buf:
            buf_type = "preamble"
        buf.append(line)
        index += 1

    flush()
    if not segments:
        return [SopSegment(text=text.strip(), block_type="preamble")]
    return segments


def split_sop_leaves(
    text: str,
    *,
    chunk_size: int,
    chunk_overlap: int,
) -> list[ChunkLeaf]:
    """Return page-local SOP leaves with step_index and block_type metadata."""
    segments = split_sop_segments(text)
    leaves: list[ChunkLeaf] = []
    search_start = 0

    for segment in segments:
        if len(segment.text) <= chunk_size:
            pieces = [segment.text]
        else:
            pieces = recursive_chunk_text(
                segment.text,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
            )

        for child_index, piece in enumerate(pieces):
            piece = piece.strip()
            if not piece:
                continue
            path, search_start = section_path_for_chunk(text, piece, search_start)
            leaves.append(
                ChunkLeaf(
                    text=piece,
                    parent_text=segment.text,
                    parent_index=max(0, (segment.step_index or 1) - 1),
                    child_index=child_index,
                    parent_chunk_id="",
                    section_path=path,
                    page_number=None,
                    step_index=segment.step_index,
                    block_type=segment.block_type,
                )
            )

    return leaves


class SopProcedureChunker:
    """Proposition-centric procedure chunker — not structure_aware."""

    def split(self, text: str, *, chunk_size: int, chunk_overlap: int) -> list[str]:
        return [leaf.text for leaf in split_sop_leaves(text, chunk_size=chunk_size, chunk_overlap=chunk_overlap)]
