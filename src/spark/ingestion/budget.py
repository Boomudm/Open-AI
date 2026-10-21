"""Per-document ingest resource budgets (Phase 3)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from spark.ingestion.errors import PermanentIngestError
from spark.ingestion.parsers.base import ParsedRecord
from spark.ingestion.reason_codes import ReasonCode


@dataclass(frozen=True)
class ResourceBudget:
    max_pages: int | None = None
    max_chunks: int | None = None
    max_embed_tokens: int | None = None
    max_ocr_pages: int | None = None


class BudgetExceeded(PermanentIngestError):
    """Non-retryable ingest failure when a document exceeds configured limits."""


def budget_from_config(config: dict[str, Any]) -> ResourceBudget:
    raw = config.get("budget") or {}
    if not isinstance(raw, dict):
        return ResourceBudget()
    return ResourceBudget(
        max_pages=_optional_int(raw.get("max_pages")),
        max_chunks=_optional_int(raw.get("max_chunks")),
        max_embed_tokens=_optional_int(raw.get("max_embed_tokens")),
        max_ocr_pages=_optional_int(raw.get("max_ocr_pages")),
    )


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)


def _estimate_tokens(text: str | None) -> int:
    normalized = (text or "").strip()
    if not normalized:
        return 0
    return max(1, len(normalized) // 4)


class ResourceBudgetTracker:
    """Runtime counters enforced while streaming parse/transform/index."""

    def __init__(self, budget: ResourceBudget) -> None:
        self.budget = budget
        self.pages_seen: int = 0
        self.chunks_seen: int = 0
        self.embed_tokens: int = 0
        self.ocr_pages: int = 0

    def record_page_count(self, page_count: int) -> None:
        if page_count <= 0:
            return
        self.pages_seen = max(self.pages_seen, page_count)
        if self.budget.max_pages is not None and self.pages_seen > self.budget.max_pages:
            self._raise("max_pages", self.pages_seen, self.budget.max_pages)

    def record_chunk(self, record: ParsedRecord) -> None:
        self.chunks_seen += 1
        if self.budget.max_chunks is not None and self.chunks_seen > self.budget.max_chunks:
            self._raise("max_chunks", self.chunks_seen, self.budget.max_chunks)

        if record.route in ("qdrant", "both"):
            tokens = _estimate_tokens(record.text_for_embedding or record.payload.get("page_content"))
            self.embed_tokens += tokens
            if self.budget.max_embed_tokens is not None and self.embed_tokens > self.budget.max_embed_tokens:
                self._raise("max_embed_tokens", self.embed_tokens, self.budget.max_embed_tokens)

        if record.payload.get("ocr_rejected") or record.payload.get("extraction_source") == "ocr":
            self.ocr_pages += 1
            if self.budget.max_ocr_pages is not None and self.ocr_pages > self.budget.max_ocr_pages:
                self._raise("max_ocr_pages", self.ocr_pages, self.budget.max_ocr_pages)

    def _raise(self, limit_name: str, observed: int, limit: int) -> None:
        detail = f"{limit_name} exceeded: {observed} > {limit}"
        raise BudgetExceeded(ReasonCode.BUDGET_EXCEEDED.value, detail)
