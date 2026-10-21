"""Layout-aware PDF parsing (remediation v3 Phase 1)."""

from spark.ingestion.parse.layout.adapter import LayoutParser, get_layout_parser
from spark.ingestion.parse.layout.types import LayoutBlock, LayoutPage, LayoutTable

__all__ = [
    "LayoutBlock",
    "LayoutPage",
    "LayoutParser",
    "LayoutTable",
    "get_layout_parser",
]
