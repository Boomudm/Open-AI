"""Tests for Qdrant collection suffix versioning (Phase 11)."""

from __future__ import annotations

from spark.core.qdrant_strategy import apply_collection_suffix, collection_for


def test_collection_suffix_appended(monkeypatch) -> None:
    from spark.core.config import settings

    monkeypatch.setattr(settings, "qdrant_collection_suffix_version", "v2")
    monkeypatch.setattr(settings, "qdrant_shard_strategy", "per_factory")
    name = collection_for("F-01", "knowledge")
    assert name.endswith("__v2")
    assert "f-01" in name.lower()


def test_apply_collection_suffix_empty_unchanged() -> None:
    assert apply_collection_suffix("spark_docs") == "spark_docs"
