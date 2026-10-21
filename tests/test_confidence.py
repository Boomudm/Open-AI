"""Phase 12 — confidence tier provenance."""

from __future__ import annotations

from spark.retrieval.confidence import confidence_from_rag, confidence_from_sql


def test_confidence_high_when_ce_active_and_strong_retrieval() -> None:
    conf = confidence_from_rag(
        top_doc_score=0.62,
        source_count=2,
        fallback_level=0,
        answer_path="grounded_llm",
        citations_verified=True,
        rerank_degraded_policy="ce_active",
    )
    assert conf.tier == "high"


def test_confidence_low_when_citations_unverified() -> None:
    conf = confidence_from_rag(
        top_doc_score=0.9,
        source_count=2,
        fallback_level=0,
        answer_path="grounded_llm",
        citations_verified=False,
    )
    assert conf.tier == "low"


def test_confidence_low_when_no_sources_even_with_high_score() -> None:
    conf = confidence_from_rag(
        top_doc_score=0.9,
        source_count=0,
        fallback_level=0,
        answer_path="grounded_llm",
        citations_verified=True,
    )
    assert conf.tier == "low"


def test_confidence_low_when_fallback_high() -> None:
    conf = confidence_from_rag(
        top_doc_score=0.8,
        source_count=3,
        fallback_level=2,
        answer_path="grounded_llm",
        citations_verified=True,
    )
    assert conf.tier == "low"


def test_confidence_medium_when_degraded_rerank() -> None:
    conf = confidence_from_rag(
        top_doc_score=0.6,
        source_count=2,
        fallback_level=1,
        answer_path="grounded_llm",
        citations_verified=True,
        rerank_degraded_policy="ce_timeout_fusion_only",
    )
    assert conf.tier == "medium"


def test_sql_confidence_ok_path() -> None:
    conf = confidence_from_sql(reason_code="ok", row_count=3, fallback_level=0)
    assert conf.tier == "high"


def test_sql_confidence_failed_path() -> None:
    conf = confidence_from_sql(reason_code="sql_error", row_count=0, fallback_level=1)
    assert conf.tier == "medium"
