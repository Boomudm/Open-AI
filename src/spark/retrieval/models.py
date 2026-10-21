from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from spark.schemas.rag import coerce_source_page


@dataclass
class RAGFilter:
    factory_id: str | None = None
    machine_id: str | None = None
    document_category: str | None = None
    document_type: str | None = None
    language: str | None = None
    only_active: bool = False
    latest_revision_only: bool = False
    revision: str | None = None
    drawing_no: str | None = None


@dataclass
class RetrievedDoc:
    page_content: str
    score: float  # rank score (vector + small lexical boost, or fused score)
    vector_score: float
    payload: dict[str, Any]
    # Lexical recovery strength (keyword/FTS), separate from the dense cosine in
    # vector_score so the two signals are never conflated on one scale.
    lexical_score: float = 0.0
    # Normalized (0..1) Reciprocal Rank Fusion score from the dense+lexical fusion stage.
    # Orders candidates into the cross-encoder; used as the degraded-mode relevance when
    # the reranker model is unavailable.
    fusion_score: float | None = None


@dataclass(frozen=True)
class RAGStreamPhaseMeta:
    """Emitted after retrieval completes, before generation tokens (stream path)."""

    retrieval_report: dict[str, Any] | None
    system_degradation: dict[str, Any] | None


@dataclass(frozen=True)
class RAGStreamToken:
    """Generation delta — provisional until citation validation completes."""

    delta: str
    provisional: bool = False


@dataclass(frozen=True)
class RAGStreamError:
    """Terminal generation failure surfaced on the stream path."""

    code: str
    message: str = ""


@dataclass(frozen=True)
class RAGStreamCitationBlock:
    """Verified final answer — replaces provisional stream text in the UI."""

    text: str
    citations_verified: bool = True


@dataclass
class RAGResult:
    answer: str
    sources: list[dict[str, Any]] = field(default_factory=list)
    used_filters: dict[str, Any] = field(default_factory=dict)
    fallback_level: int = 0
    intent: str = "factual"
    top_doc_score: float = 0.0
    answer_path: str = "unknown"
    retrieval_sources: list[str] = field(default_factory=list)
    retrieval_snapshot: dict[str, Any] | None = None
    retrieval_report: dict[str, Any] | None = None
    system_degradation: dict[str, Any] | None = None
    clarification_suggested: bool = False


def default_latest_revision_only(document_type: str | None) -> bool:
    # Product decision 2026-07: no automatic latest-revision filtering — a
    # manual uploaded without revision metadata must never be hidden from
    # answers. Callers can still request latest_revision_only explicitly;
    # outdated documents are managed via the frontend.
    return False


def _build_qdrant_filter(
    rf: RAGFilter,
    allowed_doc_ids: list[str] | None = None,
):
    from spark.retrieval.vector.filters import build_qdrant_filter

    return build_qdrant_filter(rf, allowed_doc_ids=allowed_doc_ids)


def _payload_to_source(
    payload: dict[str, Any],
    doc: RetrievedDoc,
    *,
    spans: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    doc_id = payload.get("doc_id")
    view_url = f"/api/v1/documents/{doc_id}/file" if doc_id else None
    out: dict[str, Any] = {
        "doc_id": doc_id,
        "chunk_id": payload.get("chunk_id"),
        "title": payload.get("title"),
        "source_file": payload.get("source_file"),
        "page": coerce_source_page(payload.get("page")),
        "source_sheet": payload.get("source_sheet"),
        "row_number": payload.get("row_number"),
        "extraction_source": payload.get("extraction_source"),
        "document_type": payload.get("document_type"),
        "score": round(float(doc.score), 4),
        "view_url": view_url,
        "can_view": bool(doc_id),
        # AI-interpreted (e.g. vision-extracted diagram) evidence not yet
        # verified by a human — the UI must surface a review warning.
        "needs_review": bool(payload.get("needs_review")) or None,
    }
    if spans:
        out["spans"] = spans
    return out


def cited_docs_to_sources(question: str, docs: list[RetrievedDoc]) -> list[dict[str, Any]]:
    """Build API source dicts with span offsets for cited retrieval docs."""
    from spark.generation.citations import collect_source_spans
    from spark.generation.evidence_spans import select_evidence_spans
    from spark.generation.parent_context import doc_chunk_id

    if not docs:
        return []
    spans = select_evidence_spans(question, docs)
    span_dict: dict[str, list[dict[str, Any]]] = {}
    for span in collect_source_spans(docs, spans):
        cid = str(span.get("chunk_id") or "").lower()
        span_dict.setdefault(cid, []).append(span)
    out: list[dict[str, Any]] = []
    for doc in docs:
        cid = doc_chunk_id(doc)
        out.append(
            _payload_to_source(
                doc.payload,
                doc,
                spans=span_dict.get((cid or "").lower(), []) if cid else None,
            )
        )
    return out
