"""Phase 5 — retrieval-phase meta includes degradation before generation tokens."""

from __future__ import annotations

import uuid

import pytest

from spark.core.config import settings
from spark.generation.policy import GenerationPolicy
from spark.retrieval.models import RAGFilter, RAGStreamPhaseMeta, RAGStreamToken, RetrievedDoc
from spark.retrieval.service import RAGService, _RetrievalBundle


@pytest.mark.asyncio
async def test_query_stream_yields_phase_meta_before_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "spark_stream_live_tokens", True)
    chunk_id = str(uuid.uuid4())
    doc = RetrievedDoc(
        page_content="Operating pressure must stay below 5 bar.",
        score=0.9,
        vector_score=0.9,
        payload={
            "chunk_id": chunk_id,
            "document_type": "machine_manual",
            "source_file": "manual.pdf",
        },
    )
    svc = RAGService()

    async def fake_resolve(*_args, **_kwargs):
        return _RetrievalBundle(
            docs=[doc],
            fallback_level=0,
            used_filters={},
            top_doc_score=0.9,
            scope_rf=RAGFilter(factory_id="F-01"),
            retrieval_report={"degraded": True, "rerank_degraded_policy": "fusion_only"},
        )

    class StreamingFakeLLM:
        async def astream(self, _payload):
            yield type("Chunk", (), {"content": "Pressure "})()
            yield type("Chunk", (), {"content": f"5 bar [chunk_id:{chunk_id}]"})()

        async def ainvoke(self, _payload):
            raise AssertionError("ainvoke should not run when astream succeeds")

    async def fake_policy(*_args, **_kwargs):
        return GenerationPolicy(
            extractive_first_for_safety_types=False,
            extractive_first_for_procedure=False,
        )

    monkeypatch.setattr(svc, "_resolve_retrieval", fake_resolve)
    monkeypatch.setattr(svc, "_get_llm", lambda: StreamingFakeLLM())
    monkeypatch.setattr(
        "spark.retrieval.service.resolve_generation_policy",
        fake_policy,
    )

    items: list[object] = []
    async for item in svc._query_stream_impl(
        "pressure limit?",
        RAGFilter(factory_id="F-01"),
        4,
        0.0,
        None,
        circuit_enabled=True,
    ):
        items.append(item)

    assert items
    # First event is the immediate "searching" phase marker (no degradation
    # info yet); the post-retrieval phase meta carries the degradation report.
    assert isinstance(items[0], RAGStreamPhaseMeta)
    assert items[0].retrieval_report == {"phase": "searching"}
    metas = [item for item in items if isinstance(item, RAGStreamPhaseMeta)]
    meta = next(m for m in metas if (m.retrieval_report or {}).get("degraded") is True)
    assert meta.system_degradation is not None
    token_items = [item for item in items if isinstance(item, (str, RAGStreamToken))]
    assert token_items
    assert items.index(meta) < items.index(token_items[0])
