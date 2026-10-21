from __future__ import annotations

import pytest

from spark.core.config import settings
from spark.core.llm_profile import load_llm_profile
from spark.ingestion.embedder import Embedder, SentenceTransformerEmbeddings


def test_active_profiles_use_bge_m3_sentence_transformers() -> None:
    for name in ("demo", "gemma", "prod", "rag_th"):
        profile = load_llm_profile(name)
        assert profile["embed_provider"] == "sentence_transformers"
        assert profile["embed_model"] == "BAAI/bge-m3"
        assert profile["embed_dim"] == 1024


def test_gemma_remote_uses_local_sentence_transformers_and_sparse_tokenizer() -> None:
    # gemma_remote: LLM via gateway, embedding runs locally via sentence-transformers
    # (gateway does not expose /v1/embeddings; local embed avoids network latency).
    # sparse_embed_model must always be the full HuggingFace id (not a gateway alias).
    profile = load_llm_profile("gemma_remote")
    assert profile["embed_provider"] == "sentence_transformers"
    assert profile["embed_model"] == "BAAI/bge-m3"
    assert profile["sparse_embed_model"] == "BAAI/bge-m3"
    assert profile["embed_dim"] == 1024


def test_build_returns_sentence_transformer_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "llm_profile", "demo")
    load_llm_profile.cache_clear()
    try:
        backend = Embedder()._build()
        assert isinstance(backend, SentenceTransformerEmbeddings)
        assert backend.model_name == "BAAI/bge-m3"
        assert backend.normalize is True
    finally:
        load_llm_profile.cache_clear()


def test_sentence_transformer_embeddings_requests_normalized_vectors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import numpy as np

    import spark.ingestion.index.embedder as emb_mod

    captured: dict[str, object] = {}

    class FakeModel:
        def encode(self, texts, **kwargs):
            captured.update(kwargs)
            return np.zeros((len(texts), 1024), dtype="float32")

    monkeypatch.setattr(emb_mod, "_load_sentence_transformer", lambda _name: FakeModel())

    backend = SentenceTransformerEmbeddings("BAAI/bge-m3")
    vector = backend.embed_query("MC-001 ร้อนผิดปกติ")

    assert len(vector) == 1024
    assert captured["normalize_embeddings"] is True


@pytest.mark.asyncio
async def test_embed_documents_rejects_dimension_mismatch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "llm_profile", "demo")  # expects 1024
    load_llm_profile.cache_clear()

    class WrongDimBackend:
        def embed_documents(self, texts):
            return [[0.0] * 768 for _ in texts]

    embedder = Embedder()
    embedder._model = WrongDimBackend()  # type: ignore[assignment]
    try:
        with pytest.raises(RuntimeError, match="dimension mismatch"):
            await embedder.embed_documents(["hello"])
    finally:
        load_llm_profile.cache_clear()


@pytest.mark.asyncio
async def test_embed_query_accepts_correct_dimension(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "llm_profile", "demo")  # expects 1024
    monkeypatch.setattr(settings, "rag_query_embedding_cache_ttl", 0)
    load_llm_profile.cache_clear()

    class GoodBackend:
        def embed_query(self, _text):
            return [0.01] * 1024

    embedder = Embedder()
    embedder._model = GoodBackend()  # type: ignore[assignment]
    try:
        vector = await embedder.embed_query("hello")
        assert len(vector) == 1024
    finally:
        load_llm_profile.cache_clear()
