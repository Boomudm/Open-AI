"""Tests for context budget token counting and doc trimming."""

from __future__ import annotations

from spark.retrieval.context_budget import (
    ChatMessageSlice,
    build_rag_context_budget,
    count_tokens,
    fit_docs_to_budget,
    fit_messages_to_budget,
)
from spark.retrieval.models import RetrievedDoc


def test_count_tokens_non_empty() -> None:
    assert count_tokens("hello world") > 0
    assert count_tokens("สวัสดีครับ") > 0


def test_build_rag_context_budget_positive_doc_budget() -> None:
    budget = build_rag_context_budget("MC-001 ร้อนผิดปกติ")
    assert budget.doc_budget_tokens >= 512
    assert budget.max_context_tokens >= budget.doc_budget_tokens


def test_fit_docs_to_budget_drops_lowest_score_last() -> None:
    docs = [
        RetrievedDoc(
            page_content="A" * 4000,
            score=0.9,
            vector_score=0.9,
            payload={"source_file": "high.pdf", "document_type": "machine_manual"},
        ),
        RetrievedDoc(
            page_content="B" * 4000,
            score=0.5,
            vector_score=0.5,
            payload={"source_file": "low.pdf", "document_type": "machine_manual"},
        ),
    ]
    result = fit_docs_to_budget(docs, budget_tokens=800)
    assert len(result.docs) >= 1
    assert result.docs[0].payload["source_file"] == "high.pdf"
    assert result.trimmed_chunks >= 1


def test_fit_messages_to_budget_keeps_recent() -> None:
    messages = [
        ChatMessageSlice(role="user", content="old question"),
        ChatMessageSlice(role="assistant", content="old answer"),
        ChatMessageSlice(role="user", content="new question"),
    ]
    kept = fit_messages_to_budget(messages, budget_tokens=count_tokens("new question") + 20)
    assert kept
    assert kept[-1].content == "new question"
