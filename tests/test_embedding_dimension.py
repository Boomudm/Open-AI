from __future__ import annotations

import pytest

from spark.core.config import settings
from spark.core.llm_profile import embedding_dimension, load_llm_profile
from spark.core.qdrant import _ensured_collections, ensure_collection


@pytest.fixture(autouse=True)
def _reset_ensure_collection_memo():
    # ensure_collection() memoizes per collection name for the process
    # lifetime; without a reset the mismatch test below short-circuits on the
    # entry added by the create test and never validates dimensions.
    _ensured_collections.clear()
    yield
    _ensured_collections.clear()


def test_embedding_dimension_uses_active_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "llm_profile", "prod")
    load_llm_profile.cache_clear()

    assert embedding_dimension() == 1024

    load_llm_profile.cache_clear()


def test_embedding_dimension_falls_back_to_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "llm_profile", "missing-profile")
    monkeypatch.setattr(settings, "ollama_embed_dim", 384)
    load_llm_profile.cache_clear()

    assert embedding_dimension() == 384

    load_llm_profile.cache_clear()


def test_ensure_collection_creates_with_profile_dimension(monkeypatch: pytest.MonkeyPatch) -> None:
    created: dict[str, int] = {}

    class FakeClient:
        def get_collection(self, _collection: str):
            raise ValueError("missing")

        def create_collection(
            self,
            *,
            collection_name: str,
            vectors_config,
            on_disk_payload: bool,
            sparse_vectors_config=None,
            **kwargs,
        ):
            if isinstance(vectors_config, dict):
                dense = vectors_config.get("dense") or next(iter(vectors_config.values()))
                created[collection_name] = dense.size
            else:
                created[collection_name] = vectors_config.size

        def create_payload_index(self, **_kwargs):
            return None

    monkeypatch.setattr(settings, "llm_profile", "prod")
    load_llm_profile.cache_clear()
    monkeypatch.setattr("spark.core.qdrant.get_qdrant_client", lambda: FakeClient())

    ensure_collection("spark_docs_test")

    assert created["spark_docs_test"] == 1024
    load_llm_profile.cache_clear()


def test_ensure_collection_fails_on_dimension_mismatch(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Vectors:
        size = 768

    class _Params:
        vectors = _Vectors()

    class _Config:
        params = _Params()

    class _Info:
        config = _Config()

    class FakeClient:
        def get_collection(self, _collection: str):
            return _Info()

    monkeypatch.setattr("spark.core.qdrant.get_qdrant_client", lambda: FakeClient())

    with pytest.raises(RuntimeError, match="vector size is 768"):
        ensure_collection("spark_docs_test", vector_size=1024)
