"""Structure-based semantic chunking — heading and colon heuristics."""

from __future__ import annotations

from spark.ingestion.chunking.recursive import recursive_chunk_text


class SemanticHeadingChunker:
    """Split on markdown/PDF-style headings before recursive fallback."""

    def split(self, text: str, *, chunk_size: int, chunk_overlap: int) -> list[str]:
        if not text.strip():
            return []
        sections: list[str] = []
        current: list[str] = []
        for line in text.splitlines():
            stripped = line.strip()
            is_heading = stripped.startswith("#") or (
                len(stripped) < 80 and stripped.endswith(":") and stripped == stripped.upper()
            )
            if is_heading and current:
                sections.append("\n".join(current).strip())
                current = [line]
            else:
                current.append(line)
        if current:
            sections.append("\n".join(current).strip())
        if len(sections) <= 1:
            return recursive_chunk_text(text, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        chunks: list[str] = []
        for section in sections:
            if len(section) <= chunk_size:
                if section:
                    chunks.append(section)
            else:
                chunks.extend(
                    recursive_chunk_text(section, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
                )
        return [c for c in chunks if c.strip()]
