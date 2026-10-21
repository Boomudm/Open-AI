"""Multi-query dense retrieval — Thai queries also search with the glossary-expanded query."""

from __future__ import annotations

import pytest

from spark.retrieval.engine import RetrievalEngine
from spark.retrieval.models import RAGFilter, RetrievedDoc
from spark.retrieval.vector.qdrant_search import VectorSearchResult


def _doc(chunk_id: str, content: str) -> RetrievedDoc:
    return RetrievedDoc(
        page_content=content,
        score=0.8,
        vector_score=0.8,
        payload={"chunk_id": chunk_id, "doc_id": chunk_id, "source_file": "manual.pdf"},
    )


@pytest.fixture()
def engine(monkeypatch: pytest.MonkeyPatch) -> tuple[RetrievalEngine, list[str]]:
    queries_seen: list[str] = []

    async def fake_search(*, query: str, **_kwargs) -> VectorSearchResult:
        queries_seen.append(query)
        # The expanded (Latin-bearing) query finds the English-only chunk the
        # raw Thai query misses.
        if "temperature" in query or "bearing" in query:
            return VectorSearchResult(hits=[_doc("en-chunk", "Bearing temperature limit 85 C")])
        return VectorSearchResult(hits=[_doc("th-chunk", "ข้อมูลทั่วไปของเครื่อง")])

    async def fake_hydrate(_session, _docs) -> None:
        return None

    async def fake_exact(*_args, **_kwargs) -> list[RetrievedDoc]:
        return []

    import spark.retrieval.engine as engine_mod

    monkeypatch.setattr(engine_mod, "search_qdrant_hybrid", fake_search)
    monkeypatch.setattr(engine_mod, "hydrate_parent_content_from_pg", fake_hydrate)
    monkeypatch.setattr(engine_mod, "retrieve_exact_evidence_candidates", fake_exact)

    eng = RetrievalEngine(embedder=None)

    async def fake_lexical(_query, _rf, _top_k, allowed_doc_ids=None):
        return [], False

    monkeypatch.setattr(eng, "retrieve_lexical", fake_lexical)
    return eng, queries_seen


async def test_thai_query_runs_expanded_dense_leg(engine) -> None:
    eng, queries_seen = engine
    docs, _report = await eng.retrieve(
        "อุณหภูมิ ลูกปืน", RAGFilter(), top_k=4, _skip_decomposition=True
    )
    assert len(queries_seen) == 2
    assert any("bearing" in q or "temperature" in q for q in queries_seen)
    chunk_ids = {d.payload["chunk_id"] for d in docs}
    # Both the raw-query hit and the expansion-recovered English chunk survive fusion.
    assert {"th-chunk", "en-chunk"} <= chunk_ids


async def test_english_query_runs_single_dense_leg(engine) -> None:
    eng, queries_seen = engine
    await eng.retrieve(
        "bearing temperature limit", RAGFilter(), top_k=4, _skip_decomposition=True
    )
    assert len(queries_seen) == 1
