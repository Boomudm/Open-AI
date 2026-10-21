"""Thin compatibility facade — canonical imports live under ``spark.retrieval`` and ``spark.generation``.

New code must import from vertical slices directly (see ``docs/architecture/import_spine_v2.md``).
"""

from __future__ import annotations

from spark.core.config import settings
from spark.core.qdrant import ensure_collection, get_async_qdrant_client
from spark.core.qdrant_strategy import list_search_collections
from spark.generation.prompts import HUMAN_PROMPT, SYSTEM_PROMPT, rag_prompt
from spark.ingestion.embedder import Embedder
from spark.retrieval.common import log
from spark.retrieval.constants import (
    MIN_EVIDENCE_SCORE,
    MIN_EXTRACTIVE_EVIDENCE_SCORE,
    MIN_LEXICAL_FOR_REPAIR,
    MIN_RELEVANT_DOC_SCORE,
    MIN_RERANK_AVG_SCORE,
    MIN_RERANK_SCORE,
    NO_DATA_ANSWER,
    UNAVAILABLE_ANSWER,
)
from spark.retrieval.fusion import reciprocal_rank_fusion
from spark.retrieval.models import (
    RAGFilter,
    RAGResult,
    RetrievedDoc,
    _build_qdrant_filter,
    _payload_to_source,
)
from spark.retrieval.scoring import (
    _coerce_uuid_strings,
    _doc_evidence_score,
    _docs_for_symptom_action_evidence,
    _filter_machine_conflicts,
    _has_sufficient_evidence,
    _keyword_recovery_score,
    _lexical_prefilter_terms,
    _machine_anchors,
    _prefers_manual,
    _question_evidence_terms,
    _retrieval_sources_from_docs,
    _should_keep_document_type_filter,
    _without_overridden_manuals,
    passes_authoritative_relevance_gate,
)
from spark.retrieval.service import RAGService, rag_service
from spark.retrieval.synthesis import (
    _answer_has_hallucinated_numbers,
    _answer_mentions_any_source,
    _answer_too_english_for_thai_question,
    _build_context,
    _ensure_answer_citations,
    _extract_substantive_numbers,
    _format_extractive_evidence_answer,
    _is_no_data_answer,
    _latin_word_ratio,
    _order_docs_for_context,
    _select_sources_for_display,
    _source_label,
    _split_sentences,
    _thai_ratio,
)

__all__ = [
    "Embedder",
    "HUMAN_PROMPT",
    "MIN_EVIDENCE_SCORE",
    "MIN_EXTRACTIVE_EVIDENCE_SCORE",
    "MIN_LEXICAL_FOR_REPAIR",
    "MIN_RELEVANT_DOC_SCORE",
    "MIN_RERANK_AVG_SCORE",
    "MIN_RERANK_SCORE",
    "NO_DATA_ANSWER",
    "RAGFilter",
    "RAGResult",
    "RAGService",
    "RetrievedDoc",
    "SYSTEM_PROMPT",
    "UNAVAILABLE_ANSWER",
    "ensure_collection",
    "get_async_qdrant_client",
    "list_search_collections",
    "log",
    "rag_prompt",
    "rag_service",
    "passes_authoritative_relevance_gate",
    "reciprocal_rank_fusion",
    "settings",
    "_answer_has_hallucinated_numbers",
    "_answer_mentions_any_source",
    "_answer_too_english_for_thai_question",
    "_build_context",
    "_build_qdrant_filter",
    "_coerce_uuid_strings",
    "_doc_evidence_score",
    "_docs_for_symptom_action_evidence",
    "_ensure_answer_citations",
    "_extract_substantive_numbers",
    "_filter_machine_conflicts",
    "_format_extractive_evidence_answer",
    "_has_sufficient_evidence",
    "_is_no_data_answer",
    "_keyword_recovery_score",
    "_latin_word_ratio",
    "_lexical_prefilter_terms",
    "_machine_anchors",
    "_order_docs_for_context",
    "_payload_to_source",
    "_prefers_manual",
    "_question_evidence_terms",
    "_retrieval_sources_from_docs",
    "_select_sources_for_display",
    "_should_keep_document_type_filter",
    "_source_label",
    "_split_sentences",
    "_thai_ratio",
    "_without_overridden_manuals",
]
