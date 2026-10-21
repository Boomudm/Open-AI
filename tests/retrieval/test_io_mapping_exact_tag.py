"""IO-mapping PLC-tag queries get a deterministic exact-match row, not just
whatever the embedding leg ranks highest among hundreds of structurally
near-identical symlink rows."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from spark.retrieval.engine import RetrievalEngine
from spark.retrieval.intent.router import QueryIntent
from spark.retrieval.models import RAGFilter, RetrievedDoc
from spark.retrieval.tuning import RagFusionConfig


def _row_doc(src_path: str, *, tgt_path: str | None = None, score: float = 0.5) -> RetrievedDoc:
    payload = {
        "chunk_id": f"chunk-{src_path}",
        "document_type": "io_mapping",
        "source_file": "MAPPING.xlsx",
        "src_path": src_path,
    }
    if tgt_path:
        payload["tgt_path"] = tgt_path
    return RetrievedDoc(
        page_content=f"EcoRT_0 at {src_path}",
        score=score,
        vector_score=score,
        payload=payload,
    )


async def _no_multi_hop(*_a, **_kw):
    return None


def _wire_common_mocks(engine: RetrievalEngine, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(engine, "_retrieve_multi_hop", _no_multi_hop)
    monkeypatch.setattr(
        engine, "resolve_fusion_config", AsyncMock(return_value=RagFusionConfig.from_factory_config({}))
    )
    monkeypatch.setattr(engine, "resolve_lexical_engine", AsyncMock(return_value="postgres"))
    monkeypatch.setattr(engine, "_rag_circuit_enabled", AsyncMock(return_value=False))
    monkeypatch.setattr(engine, "retrieve_lexical", AsyncMock(return_value=([], False)))
    monkeypatch.setattr(engine, "_apply_rerank", None)
    monkeypatch.setattr(
        "spark.retrieval.engine.hydrate_parent_content_from_pg", AsyncMock()
    )


@pytest.mark.asyncio
async def test_exact_tag_wins_over_noisy_near_duplicate_vector_hits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Simulate the real 856-row symlink sheet: dense search's top candidates
    are all similarly-named BELT_* rows that are NOT the one asked about — the
    exact-match leg must still surface the correct row."""
    target = "RES0.BELT_Forward_Dest"
    noisy_vector_hits = [
        _row_doc("RES0.BELT_Operating_Current", score=0.91),
        _row_doc("RES0.BELT_Operating_Speed", score=0.90),
        _row_doc("RES0.BELT_Position", score=0.89),
        _row_doc("RES0.BELT_Startting_Rate", score=0.88),
    ]
    exact_row = _row_doc(target, tgt_path="RES0.SERVO_BELT.Destination", score=1.0)

    async def fake_vector(*_args, **_kwargs):
        class Result:
            hits = list(noisy_vector_hits)
            failed_collections: list[str] = []
            embed_failed = False
            sparse_encoder_id = "none"

        return Result()

    monkeypatch.setattr(
        "spark.retrieval.engine.search_qdrant_hybrid", AsyncMock(side_effect=fake_vector)
    )
    monkeypatch.setattr(
        "spark.retrieval.engine.search_qdrant_exact_tag",
        AsyncMock(return_value=[exact_row]),
    )

    engine = RetrievalEngine(embedder=AsyncMock())
    _wire_common_mocks(engine, monkeypatch)

    docs, report = await engine.retrieve(
        f"{target} เชื่อมกับอะไร", RAGFilter(factory_id="F-01"), top_k=4
    )

    assert report.intent == QueryIntent.IO_MAPPING.value
    src_paths = [d.payload.get("src_path") for d in docs]
    assert target in src_paths, f"exact tag row missing from results: {src_paths}"


@pytest.mark.asyncio
async def test_no_plc_tag_in_query_skips_exact_lookup(monkeypatch: pytest.MonkeyPatch) -> None:
    """A general question must not trigger the exact-tag scroll query at all."""
    exact_lookup = AsyncMock(return_value=[])
    monkeypatch.setattr("spark.retrieval.engine.search_qdrant_exact_tag", exact_lookup)

    async def fake_vector(*_args, **_kwargs):
        class Result:
            hits: list[RetrievedDoc] = []
            failed_collections: list[str] = []
            embed_failed = False
            sparse_encoder_id = "none"

        return Result()

    monkeypatch.setattr(
        "spark.retrieval.engine.search_qdrant_hybrid", AsyncMock(side_effect=fake_vector)
    )

    engine = RetrievalEngine(embedder=AsyncMock())
    _wire_common_mocks(engine, monkeypatch)

    await engine.retrieve("มอเตอร์ร้อนผิดปกติต้องทำอะไร", RAGFilter(factory_id="F-01"), top_k=4)

    exact_lookup.assert_not_called()
