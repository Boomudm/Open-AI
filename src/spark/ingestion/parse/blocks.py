from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

BlockType = Literal["paragraph", "heading", "table", "list", "figure", "procedure_step", "ocr_block"]


@dataclass
class ParsedBlock:
    """Pre-chunk unit emitted by parsers; chunk.registry consumes blocks."""

    block_type: BlockType
    text: str
    page: int | None = None
    bbox: tuple[float, float, float, float] | None = None
    reading_order: int = 0
    section_path: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
