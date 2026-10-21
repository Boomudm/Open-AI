"""Shared types for agentic tool wrappers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class RBACContext:
    """Server-injected RBAC — never populated from LLM tool arguments."""

    allowed_doc_ids: list[str] | None = None
    allowed_factory_ids: list[str] | None = None


@dataclass(frozen=True)
class SearchFilters:
    factory_id: str | None = None
    machine_id: str | None = None
    document_type: str | None = None
    language: str | None = None
    only_active: bool = False
    latest_revision_only: bool = False


@dataclass(frozen=True)
class DatabaseScope:
    factory_id: str | None = None
    machine_id: str | None = None


@dataclass
class SearchDocumentsResult:
    answer: str
    sources: list[dict[str, Any]] = field(default_factory=list)
    relevance_passed: bool = False
    answer_path: str = "unknown"
    latency_ms: float = 0.0


@dataclass
class QueryDatabaseResult:
    answer: str
    sql_generated: str = ""
    rows_returned: int = 0
    semantic_validation_passed: bool = False
    citation_refs: list[str] = field(default_factory=list)
    latency_ms: float = 0.0
    rows: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class AgenticSynthesisInput:
    question: str
    search_result: SearchDocumentsResult | None = None
    db_result: QueryDatabaseResult | None = None
    factory_id: str | None = None
    machine_id: str | None = None
    language: str = "th"


@dataclass
class AgenticSynthesisOutput:
    answer: str
    sources: list[dict[str, Any]] = field(default_factory=list)
    answer_path: str = "no_data"
    citations_verified: bool = False
    hallucination_guard_passed: bool = True
    latency_ms: float = 0.0
    comparator_notes: str | None = None
