from __future__ import annotations

import uuid

import pytest

from spark.core.cache import Cache
from spark.core.config import settings
from spark.ingestion.embedder import Embedder


class CountingEmbeddings:
    def __init__(self) -> None:
        self.calls = 0

    def embed_query(self, _text: str) -> list[float]:
        self.calls += 1
        return [float(self.calls), 0.25, 0.5]


@pytest.mark.asyncio
async def test_embed_query_uses_short_ttl_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    Cache._instance = None
    monkeypatch.setattr(settings, "rag_query_embedding_cache_ttl", 60)
    monkeypatch.setattr(settings, "llm_profile", f"test-cache-{uuid.uuid4()}")
    monkeypatch.setattr(settings, "ollama_embed_model", "embed-test")
    monkeypatch.setattr(settings, "ollama_embed_dim", 3)

    embedder = Embedder()
    model = CountingEmbeddings()
    embedder._model = model  # type: ignore[assignment]

    first = await embedder.embed_query("MC-001 ร้อนผิดปกติ")
    second = await embedder.embed_query("MC-001   ร้อนผิดปกติ")

    assert first == second
    assert model.calls == 1
