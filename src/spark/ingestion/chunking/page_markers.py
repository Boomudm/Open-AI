"""Cross-page document assembly and page propagation for PDF chunking."""

from __future__ import annotations

import re

PAGE_MARKER_PATTERN = re.compile(r"<!--\s*page\s+(\d+)\s*-->", re.IGNORECASE)
PAGE_MARKER_TEMPLATE = "\n\n<!-- page {page} -->\n\n"


def concat_pages_with_markers(pages: list[tuple[int, str]]) -> tuple[str, list[tuple[int, int]]]:
    """Join page bodies with HTML comment markers; return text and (offset, page) index."""
    markers: list[tuple[int, int]] = []
    parts: list[str] = []
    offset = 0
    for page_num, page_text in pages:
        marker = PAGE_MARKER_TEMPLATE.format(page=page_num)
        markers.append((offset, page_num))
        parts.append(marker)
        offset += len(marker)
        parts.append(page_text)
        offset += len(page_text)
    return "".join(parts), markers


def page_for_char_offset(markers: list[tuple[int, int]], char_offset: int) -> int:
    """Map a character offset in concatenated text to the nearest preceding page marker."""
    if not markers:
        return 1
    page = markers[0][1]
    for marker_offset, page_num in markers:
        if marker_offset <= char_offset:
            page = page_num
        else:
            break
    return page


def find_chunk_offset(full_text: str, chunk_text: str, search_start: int = 0) -> int:
    """Locate chunk text within full document text for page propagation."""
    needle = chunk_text.strip()
    if not needle:
        return search_start
    idx = full_text.find(needle, search_start)
    return idx if idx >= 0 else search_start
