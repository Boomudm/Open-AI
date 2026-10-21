"""Qdrant collection failures are logged and metered (remediation v2 Phase 8)."""

from __future__ import annotations

import pytest

from spark.core.metrics import rag_vector_collection_fail_total
from spark.retrieval.vector.shard_search import search_all_shards
from spark.retrieval.models import RetrievedDoc


@pytest.mark.asyncio
async def test_collection_failure_logged_and_metered(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    before = rag_vector_collection_fail_total.labels(collection="shard_a")._value.get()

    async def search_one(coll: str) -> list[RetrievedDoc]:
        if coll == "shard_a":
            raise RuntimeError("qdrant unavailable")
        return [
            RetrievedDoc(
                page_content="ok",
                score=0.9,
                vector_score=0.9,
                payload={"chunk_id": "c1"},
            )
        ]

    hits, failed = await search_all_shards(
        collections=["shard_a", "shard_b"],
        search_one=search_one,
        limit=10,
        factory_id="F-01",
    )

    captured = capsys.readouterr()
    assert failed == ["shard_a"]
    assert len(hits) == 1
    assert "qdrant_collection_search_failed" in captured.out
    after = rag_vector_collection_fail_total.labels(collection="shard_a")._value.get()
    assert after == before + 1
