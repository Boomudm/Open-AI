"""One chunk per table row — spare-part catalog narratives."""

from __future__ import annotations


class TableRowChunker:
    """Split on double newlines (one Excel narrative row per chunk)."""

    def split(self, text: str, *, chunk_size: int, chunk_overlap: int) -> list[str]:
        del chunk_size, chunk_overlap
        rows = [line.strip() for line in text.split("\n\n") if line.strip()]
        return rows or ([text.strip()] if text.strip() else [])
