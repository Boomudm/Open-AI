"""Section path from heading stack during structure-aware chunking."""

from __future__ import annotations

import re

HEADING_RE = re.compile(
    r"(?m)^(?:"
    r"(#{1,6})\s+(.+)"  # markdown headings
    r"|(?:ขั้นตอนที่|Step)\s*(\d+[^\n]*)"  # procedure labels
    r")"
)


def section_path_before_offset(text: str, offset: int) -> str:
    """Return breadcrumb path (last 3 headings) for text preceding *offset*."""
    prefix = text[: max(0, offset)]
    stack: list[str] = []
    for match in HEADING_RE.finditer(prefix):
        if match.group(2):
            stack.append(match.group(2).strip())
        elif match.group(3):
            stack.append(f"Step {match.group(3).strip()}")
    if not stack:
        return ""
    return " > ".join(stack[-3:])


def section_path_for_chunk(full_text: str, chunk_text: str, search_start: int) -> tuple[str, int]:
    """Locate chunk in full_text and return (section_path, new_search_start)."""
    if not chunk_text.strip():
        return "", search_start
    idx = full_text.find(chunk_text, search_start)
    if idx < 0:
        idx = full_text.find(chunk_text.strip()[: min(40, len(chunk_text))], search_start)
    if idx < 0:
        return "", search_start
    path = section_path_before_offset(full_text, idx)
    return path, max(search_start, idx + 1)
