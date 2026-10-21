from __future__ import annotations

import uuid
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from spark.core.logging import get_logger
from spark.schemas.openapi_examples import (
    RAG_FILTER_MC001,
    RAG_QUERY_OVERHEATING,
    RAG_RESPONSE_OVERHEATING,
)

_log = get_logger(__name__)


def coerce_source_page(value: Any) -> int | None:
    """Normalize Qdrant page values for SourceRef."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value == int(value):
        return int(value)
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.isdigit():
            return int(stripped)
    return None


def sources_to_refs(sources: list[dict[str, Any]]) -> list["SourceRef"]:
    refs: list[SourceRef] = []
    for raw in sources:
        try:
            refs.append(
                SourceRef(
                    doc_id=raw.get("doc_id"),
                    title=raw.get("title"),
                    source_file=raw.get("source_file"),
                    page=coerce_source_page(raw.get("page")),
                    source_sheet=raw.get("source_sheet"),
                    row_number=raw.get("row_number"),
                    extraction_source=raw.get("extraction_source"),
                    needs_review=bool(raw.get("needs_review")) if raw.get("needs_review") is not None else None,
                    document_type=raw.get("document_type"),
                    score=float(raw.get("score", 0) or 0),
                    view_url=raw.get("view_url"),
                    can_view=bool(raw.get("can_view", False)),
                    spans=[
                        SourceSpan(**span)
                        for span in (raw.get("spans") or [])
                        if isinstance(span, dict)
                    ],
                )
            )
        except Exception as exc:
            _log.warning("source_ref_skip", error=str(exc)[:120], source=raw)
    return refs


class RAGFilterModel(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [RAG_FILTER_MC001, {"factory_id": "F-01", "document_type": "knowledge_document"}]
        }
    )

    factory_id: str | None = Field(None, examples=["F-01"])
    machine_id: str | None = Field(None, examples=["MC-001"])
    document_category: str | None = Field(None, examples=["knowledge"])
    document_type: str | None = Field(None, examples=["machine_manual"])
    language: str | None = Field(None, examples=["th"])
    only_active: bool = False
    latest_revision_only: bool | None = None
    revision: str | None = Field(None, examples=["Rev C"])
    drawing_no: str | None = Field(None, examples=["EE-13"])


class SourceSpan(BaseModel):
    chunk_id: str | None = None
    start_offset: int = 0
    end_offset: int = 0
    text: str | None = None


class SourceRef(BaseModel):
    doc_id: str | None = None
    title: str | None = None
    source_file: str | None = None
    page: int | None = None
    source_sheet: str | None = None
    row_number: int | None = None
    extraction_source: str | None = None
    needs_review: bool | None = None
    document_type: str | None = None
    score: float
    view_url: str | None = None
    can_view: bool = False
    spans: list[SourceSpan] = Field(default_factory=list)


class AskRequest(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [RAG_QUERY_OVERHEATING]})

    question: str = Field(
        min_length=2,
        max_length=3000,
        examples=["Servo Motor MC-001 ร้อนผิดปกติ ต้องทำอะไร"],
    )
    filter: RAGFilterModel | None = None
    top_k: int = Field(6, ge=1, le=20)
    stream: bool = False
    allow_scope_broadening: bool = Field(
        False,
        description="Explicit consent to broaden machine scope in fallback ladder (levels 3–4).",
    )


class RetrievalReportModel(BaseModel):
    degraded: bool = False
    degraded_reasons: list[str] = Field(default_factory=list)
    failed_collections: list[str] = Field(default_factory=list)
    vector_count: int = 0
    lexical_count: int = 0
    fusion_method: str = "weighted_rrf"
    intent: str = "general"
    sparse_encoder_id: str = ""
    sparse_available: bool = True
    rerank_degraded: bool = False
    rerank_degraded_policy: str = "ce_active"


class SystemDegradationModel(BaseModel):
    vector_available: bool = True
    lexical_available: bool = True
    rerank_available: bool = True
    llm_available: bool = True
    user_message_key: str = "rag.status.healthy"
    fail_closed: bool = False
    system_status: Literal["healthy", "degraded", "critical", "unavailable"] = "healthy"
    rerank_degraded: bool = False
    rerank_degraded_policy: str = "ce_active"
    sparse_available: bool = True


class AskResponse(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [RAG_RESPONSE_OVERHEATING]})

    answer: str
    sources: list[SourceRef]
    used_filters: dict[str, Any]
    intent: Literal[
        "factual",
        "analytic",
        "followup",
        "unknown",
        "chitchat",
        "external_live",
        "compound",
        "clarification",
        "policy",
    ] = "factual"
    # "rag" pipelines, "sql" external analytics, "agentic" canary,
    # "clarify" ask-user-back turns.
    route: Literal["rag", "sql", "agentic", "clarify"] | None = None
    routing_reason: str | None = None
    fallback_level: int = 0
    cache_hit: bool = False
    assistant_message_id: uuid.UUID | None = None
    top_doc_score: float | None = None
    confidence_tier: Literal["high", "medium", "low"] | None = None
    retrieval_report: RetrievalReportModel | None = None
    system_degradation: SystemDegradationModel | None = None


class RAGQuery(AskRequest):
    pass
