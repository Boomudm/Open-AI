"""Tests for embed lineage metadata (remediation v2 Phase 1)."""

from __future__ import annotations


from spark.ingestion.embed_lineage import (
    assert_retrieval_compatible,
    embed_lineage_for_text,
    lineage_from_profile,
)
from spark.ingestion.embed_profile import EmbedProfile


def test_embed_lineage_includes_runtime_model_and_hash() -> None:
    profile = EmbedProfile(
        model_id="BAAI/bge-m3",
        provider="sentence_transformers",
        dimension=1024,
        llm_profile="demo",
    )
    lineage = embed_lineage_for_text(
        "Servo cooling fan check at 80C",
        profile=profile,
        config_hash="abc123",
    )
    assert lineage["embed_model_id"] == "BAAI/bge-m3"
    assert lineage["embed_model_version"] == "BAAI/bge-m3@sentence_transformers#1024"
    assert lineage["embed_provider"] == "sentence_transformers"
    assert lineage["config_hash"] == "abc123"
    assert len(lineage["content_hash"]) == 32
    assert lineage["chunk_schema_version"] == 2


def test_embed_lineage_hash_is_stable() -> None:
    profile = EmbedProfile(
        model_id="test-model",
        provider="ollama",
        dimension=768,
        llm_profile="demo",
    )
    a = embed_lineage_for_text("same text", profile=profile, config_hash="x")
    b = embed_lineage_for_text("same text", profile=profile, config_hash="x")
    assert a["content_hash"] == b["content_hash"]


def test_assert_retrieval_compatible_full_tuple() -> None:
    profile = EmbedProfile(
        model_id="BAAI/bge-m3",
        provider="sentence_transformers",
        dimension=1024,
        llm_profile="demo",
    )
    expected = lineage_from_profile(profile, "cfg")
    payload = {
        "embed_model_id": expected.embed_model_id,
        "embed_model_version": expected.embed_model_version,
        "embed_provider": expected.embed_provider,
        "chunk_schema_version": expected.chunk_schema_version,
    }
    assert assert_retrieval_compatible(payload, expected=expected)
    assert not assert_retrieval_compatible(
        {**payload, "embed_model_id": "other-model"},
        expected=expected,
    )
