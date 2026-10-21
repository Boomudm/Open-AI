"""Layout-aware parse types (remediation v3 Phase 1)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

LayoutBlockType = Literal["text", "heading", "table", "list", "figure_caption"]


@dataclass(frozen=True)
class LayoutBlock:
    block_id: str
    page_number: int
    block_type: LayoutBlockType
    text: str
    section_path: tuple[str, ...] = ()
    ocr_confidence: float | None = None
    bbox: tuple[float, float, float, float] | None = None
    extraction_source: str = "pypdf"


@dataclass(frozen=True)
class LayoutTable:
    page_number: int
    table_index: int
    headers: list[str]
    rows: list[list[str]]
    markdown: str


@dataclass
class LayoutPage:
    page_number: int
    blocks: list[LayoutBlock] = field(default_factory=list)
    ocr_confidence: float | None = None
    extraction_source: str = "pypdf"
