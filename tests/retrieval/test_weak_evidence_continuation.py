"""Weak-evidence continuation — non-safety questions with real candidates reach
generation instead of being refused by the lexical evidence gate; genuinely
empty retrieval returns the helpful no-data message."""

from __future__ import annotations

import time

import pytest

from spark.retrieval.models import RAGFilter, RetrievedDoc
from spark.retrieval.service import RAGService, _EarlyRAGResult, _RetrievalBundle


def _doc(score: float) -> RetrievedDoc:
    return RetrievedDoc(
        page_content="KR C5 micro controller weight 25 kg",
        score=score,
        vector_score=score,
        payload={
            "chunk_id": "chunk-1",
            "doc_id": "doc-1",
            "title": "KUKA KR C5 Manual",
            "source_file": "krc5.pdf",
            "document_type": "machine_manual",
        },
    )


@pytest.fixture()
def gated_service(monkeypatch: pytest.MonkeyPatch):
    """RAGService whose retrieval returns docs that FAIL the evidence gate."""
    svc = RAGService()
    docs_holder: dict[str, list[RetrievedDoc]] = {"docs": []}

    async def fake_retrieve(_question, _rf, _top_k, _allowed, **_kwargs):
        return docs_holder["docs"]

    monkeypatch.setattr(svc, "_retrieve", fake_retrieve)
    monkeypatch.setattr(svc, "_passes_relevance", lambda *_a, **_k: False)
    return svc, docs_holder


async def test_non_safety_weak_candidates_continue_to_generation(gated_service) -> None:
    svc, holder = gated_service
    holder["docs"] = [_doc(score=0.5)]
    resolved = await svc._resolve_retrieval(
        "น้ำหนักของ controller เท่าไหร่",
        RAGFilter(),
        top_k=4,
        _start=time.perf_counter(),
    )
    assert isinstance(resolved, _RetrievalBundle)
    assert resolved.used_filters.get("evidence_weak") is True
    assert resolved.docs


async def test_below_floor_returns_helpful_no_data(gated_service) -> None:
    svc, holder = gated_service
    holder["docs"] = [_doc(score=0.02)]
    resolved = await svc._resolve_retrieval(
        "น้ำหนักของ controller เท่าไหร่",
        RAGFilter(),
        top_k=4,
        _start=time.perf_counter(),
    )
    assert isinstance(resolved, _EarlyRAGResult)
    assert resolved.result.answer_path == "no_data"
    # Helpful message: names the near-miss document and gives suggestions.
    assert "KUKA KR C5 Manual" in resolved.result.answer
    assert "คำแนะนำ" in resolved.result.answer


async def test_safety_question_still_fails_closed(gated_service) -> None:
    from spark.retrieval.constants import NO_DATA_ANSWER

    svc, holder = gated_service
    holder["docs"] = [_doc(score=0.5)]
    resolved = await svc._resolve_retrieval(
        "ขั้นตอน lockout tagout ก่อนซ่อม",
        RAGFilter(),
        top_k=4,
        _start=time.perf_counter(),
    )
    assert isinstance(resolved, _EarlyRAGResult)
    assert resolved.result.answer == NO_DATA_ANSWER
