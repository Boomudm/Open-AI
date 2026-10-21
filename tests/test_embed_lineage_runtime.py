"""Runtime embed profile lineage — different LLM profiles produce distinct versions."""

from __future__ import annotations

from unittest.mock import patch

from spark.ingestion.embed_lineage import embed_lineage_for_text
from spark.ingestion.embed_profile import EmbedProfile


def test_different_profiles_produce_distinct_lineage_versions() -> None:
    demo = EmbedProfile(
        model_id="BAAI/bge-m3",
        provider="sentence_transformers",
        dimension=1024,
        llm_profile="demo",
    )
    remote = EmbedProfile(
        model_id="text-embedding-3-large",
        provider="openai",
        dimension=3072,
        llm_profile="gemma_remote",
    )
    demo_lineage = embed_lineage_for_text("query", profile=demo, config_hash="h1")
    remote_lineage = embed_lineage_for_text("query", profile=remote, config_hash="h1")
    assert demo_lineage["embed_model_id"] != remote_lineage["embed_model_id"]
    assert demo_lineage["embed_model_version"] != remote_lineage["embed_model_version"]
    assert demo_lineage["embed_provider"] == "sentence_transformers"
    assert remote_lineage["embed_provider"] == "openai"


def test_embedder_exposes_runtime_profile() -> None:
    with patch(
        "spark.ingestion.embed_profile.load_llm_profile",
        return_value={
            "embed_provider": "sentence_transformers",
            "embed_model": "BAAI/bge-m3",
            "embed_dim": 1024,
        },
    ), patch(
        "spark.ingestion.embed_profile.embedding_dimension",
        return_value=1024,
    ), patch(
        "spark.ingestion.embed_profile.settings.llm_profile",
        "demo",
    ):
        from spark.ingestion.index.embedder import Embedder

        Embedder._instance = None
        profile = Embedder.get().embed_profile()
        assert profile.model_id == "BAAI/bge-m3"
        assert profile.version == "BAAI/bge-m3@sentence_transformers#1024"
