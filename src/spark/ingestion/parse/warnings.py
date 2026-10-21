"""Parse-time warnings surfaced in ingestion job events."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class TableExtractWarning:
    """PDF table extraction failed — loss is visible, not silent."""

    file: str
    error: str
    page_count: int | None = None

    def to_event(self) -> dict[str, Any]:
        return {
            "code": "table_extract_warning",
            "level": "warning",
            "file": self.file,
            "error": self.error[:500],
            "page_count": self.page_count,
        }


@dataclass
class OCRQualityWarning:
    """Document-level OCR confidence fell below the quality threshold — tagged, not blocked."""

    file: str
    detail: str
    document_type: str | None = None

    def to_event(self) -> dict[str, Any]:
        return {
            "code": "ocr_quality_low",
            "level": "warning",
            "file": self.file,
            "error": self.detail[:500],
            "document_type": self.document_type,
        }


@dataclass
class ParseWarningCollector:
    warnings: list[dict[str, Any]] = field(default_factory=list)

    def add(self, warning: TableExtractWarning | OCRQualityWarning) -> None:
        self.warnings.append(warning.to_event())

    def extend(self, items: list[dict[str, Any]]) -> None:
        self.warnings.extend(items)
