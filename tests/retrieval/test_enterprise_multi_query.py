"""Enterprise dense retrieval also runs the glossary-expanded query leg."""

from __future__ import annotations

import pytest

from spark.retrieval.enterprise_service import EnterpriseRAGService
from spark.retrieval.models import RAGFilter, RetrievedDoc


class _Result:
    def __init__(self, hits):
        self.hits = hits
        self.embed_failed = False


def _doc(chunk_id: str, score: float) -> RetrievedDoc:
    return RetrievedDoc(
        page_content="content",
        score=score,
        vector_score=score,
        payload={"chunk_id": chunk_id, "source_file": "handbook.pdf"},
    )


async def test_enterprise_thai_query_merges_expanded_leg(monkeypatch: pytest.MonkeyPatch) -> None:
    queries: list[str] = []

    async def fake_search(*, query: str, **_kwargs):
        queries.append(query)
        if "salary" in query:
            return _Result([_doc("en-chunk", 0.7), _doc("shared", 0.9)])
        return _Result([_doc("shared", 0.6), _doc("th-chunk", 0.5)])

    import spark.retrieval.vector.enterprise_search as search_mod

    monkeypatch.setattr(search_mod, "search_enterprise_dense", fake_search)
    monkeypatch.setattr(EnterpriseRAGService, "embedder", property(lambda self: None))

    svc = EnterpriseRAGService()
    hits = await svc._retrieve("เงินเดือนออกวันไหน", RAGFilter(factory_id="E-03"), top_k=4)

    assert len(queries) == 2
    ids = [d.payload["chunk_id"] for d in hits]
    assert "en-chunk" in ids and "th-chunk" in ids
    shared = next(d for d in hits if d.payload["chunk_id"] == "shared")
    # Merged by best score across legs.
    assert shared.score == 0.9
    assert ids[0] == "shared"


async def test_enterprise_english_query_single_leg(monkeypatch: pytest.MonkeyPatch) -> None:
    queries: list[str] = []

    async def fake_search(*, query: str, **_kwargs):
        queries.append(query)
        return _Result([_doc("only", 0.8)])

    import spark.retrieval.vector.enterprise_search as search_mod

    monkeypatch.setattr(search_mod, "search_enterprise_dense", fake_search)
    monkeypatch.setattr(EnterpriseRAGService, "embedder", property(lambda self: None))

    svc = EnterpriseRAGService()
    hits = await svc._retrieve("payroll date policy", RAGFilter(), top_k=4)
    assert len(queries) == 1
    assert [d.payload["chunk_id"] for d in hits] == ["only"]
