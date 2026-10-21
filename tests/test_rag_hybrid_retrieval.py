from __future__ import annotations

import pytest

from spark.core.metrics import rag_lexical_degraded_total
from spark.services.rag_service import (
    RAGFilter,
    RAGService,
    RetrievedDoc,
    _keyword_recovery_score,
)


def test_keyword_recovery_bridges_thai_question_to_english_manual_terms() -> None:
    question = "Servo Motor MC-001 ร้อนผิดปกติ ต้องทำอะไร"
    manual_payload = {
        "page_content": (
            "WARNING: Check cooling fan if temperature exceeds 80°C. "
            "Stop the servo motor immediately."
        ),
        "machine_id": "MC-001",
        "source_file": "manual.pdf",
    }
    unrelated_payload = {
        "page_content": "Warranty period and package label storage instructions.",
        "machine_id": "MC-001",
        "source_file": "manual.pdf",
    }

    assert _keyword_recovery_score(question, manual_payload) >= 0.18
    assert _keyword_recovery_score(question, unrelated_payload) < 0.18


@pytest.mark.asyncio
async def test_lexical_recovery_returns_postgres_hits(monkeypatch: pytest.MonkeyPatch) -> None:
    pg_doc = RetrievedDoc(
        page_content=(
            "WARNING: Check cooling fan if temperature exceeds 80°C. "
            "Stop the servo motor immediately."
        ),
        score=0.91,
        vector_score=0.0,
        lexical_score=0.91,
        payload={
            "source_file": "manual.pdf",
            "machine_id": "MC-001",
            "retrieval_mode": "postgres_lexical_v2",
        },
    )

    async def fake_pg(*_args, **_kwargs):
        return [pg_doc]

    monkeypatch.setattr(RAGService, "_retrieve_postgres_lexical_candidates", fake_pg)

    docs = await RAGService()._retrieve_lexical_candidates(
        "Servo Motor MC-001 ร้อนผิดปกติ ต้องทำอะไร",
        RAGFilter(machine_id="MC-001"),
        top_k=3,
    )

    assert len(docs) == 1
    assert docs[0].payload["source_file"] == "manual.pdf"
    assert docs[0].payload["retrieval_mode"] == "postgres_lexical_v2"
    assert docs[0].score >= 0.18
    assert docs[0].lexical_score == docs[0].score
    assert docs[0].vector_score == 0.0


@pytest.mark.asyncio
async def test_retrieve_falls_back_to_lexical_when_embedding_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pg_doc = RetrievedDoc(
        page_content=(
            "WARNING: Check cooling fan if temperature exceeds 80°C. "
            "Stop the servo motor immediately."
        ),
        score=0.91,
        vector_score=0.0,
        lexical_score=0.91,
        payload={
            "source_file": "manual.pdf",
            "machine_id": "MC-001",
            "page": 13,
            "document_type": "machine_manual",
            "retrieval_mode": "postgres_lexical_v2",
        },
    )

    async def fake_lexical(*_args, **_kwargs):
        return [pg_doc], False

    from spark.retrieval.vector.qdrant_search import VectorSearchResult

    async def fake_vector(*_args, **_kwargs):
        return VectorSearchResult(hits=[], embed_failed=True)

    async def passthrough_rerank(_query, docs, _top_k, **kwargs):
        return docs

    svc = RAGService()
    monkeypatch.setattr("spark.retrieval.engine.search_qdrant_hybrid", fake_vector)
    monkeypatch.setattr(svc.retrieval_engine, "retrieve_lexical", fake_lexical)
    monkeypatch.setattr(svc, "_apply_retrieval_rerank_async", passthrough_rerank)
    monkeypatch.setattr("spark.core.config.settings.rag_lexical_scan_limit", 10)
    monkeypatch.setattr("spark.core.config.settings.rag_lexical_min_score", 0.18)

    docs = await svc._retrieve(
        "Servo Motor MC-001 ร้อนผิดปกติ ต้องทำอะไร",
        RAGFilter(machine_id="MC-001"),
        top_k=3,
    )

    assert docs
    assert docs[0].payload["source_file"] == "manual.pdf"
    assert docs[0].payload["retrieval_mode"] == "postgres_lexical_v2"


@pytest.mark.asyncio
async def test_vector_retrieval_keeps_raw_question_as_primary_leg(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The user's own wording is always dense-searched VERBATIM.

    Multi-query expansion adds a SEPARATE second dense leg for the glossary-
    expanded query — it must never mutate the raw-question leg."""
    seen: list[str] = []

    from spark.retrieval.vector.qdrant_search import VectorSearchResult

    async def fake_vector(*, query, **_kwargs):
        seen.append(query)
        return VectorSearchResult(hits=[])

    async def fake_lexical(*_args, **_kwargs):
        return [], False

    async def passthrough_rerank(_query, docs, _top_k, **kwargs):
        return docs

    svc = RAGService()
    monkeypatch.setattr("spark.retrieval.engine.search_qdrant_hybrid", fake_vector)
    monkeypatch.setattr(svc.retrieval_engine, "retrieve_lexical", fake_lexical)
    monkeypatch.setattr(svc, "_apply_retrieval_rerank_async", passthrough_rerank)

    await svc._retrieve("MC-001 ลูกปืนร้อน ต้องซ่อมไหม", RAGFilter(), top_k=1)

    assert "MC-001 ลูกปืนร้อน ต้องซ่อมไหม" in seen
    raw_leg = next(q for q in seen if q == "MC-001 ลูกปืนร้อน ต้องซ่อมไหม")
    assert "Expanded search terms" not in raw_leg
    # Thai bearing/overheat terms expand into a second, separate dense leg.
    expanded_legs = [q for q in seen if q != raw_leg]
    assert expanded_legs and any("bearing" in q for q in expanded_legs)


@pytest.mark.asyncio
async def test_lexical_recovery_uses_postgres(monkeypatch: pytest.MonkeyPatch) -> None:
    svc = RAGService()
    pg_doc = RetrievedDoc(
        page_content="WARNING: Check cooling fan if temperature exceeds 80°C.",
        score=0.93,
        vector_score=0.0,
        lexical_score=0.93,
        payload={"source_file": "manual.pdf", "retrieval_mode": "postgres_lexical_v2"},
    )

    async def fake_pg(*_args, **_kwargs):
        return [pg_doc]

    monkeypatch.setattr(svc, "_retrieve_postgres_lexical_candidates", fake_pg)

    docs = await svc._retrieve_lexical_candidates("MC-001 ร้อน", RAGFilter(), top_k=3)

    assert docs == [pg_doc]


@pytest.mark.asyncio
async def test_lexical_degraded_returns_empty_on_postgres_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    svc = RAGService()

    async def broken_pg(*_args, **_kwargs):
        raise RuntimeError("missing mirror column")

    monkeypatch.setattr(svc, "_retrieve_postgres_lexical_candidates", broken_pg)
    async def fake_engine(_rf):
        return "postgres_thai_v3"

    monkeypatch.setattr(svc, "_resolve_lexical_engine", fake_engine)

    before = rag_lexical_degraded_total.labels(engine="postgres_thai_v3", reason="RuntimeError")._value.get()

    docs = await svc._retrieve_lexical_candidates("MC-001 ร้อน", RAGFilter(), top_k=3)

    assert docs == []
    after = rag_lexical_degraded_total.labels(engine="postgres_thai_v3", reason="RuntimeError")._value.get()
    assert after == before + 1
