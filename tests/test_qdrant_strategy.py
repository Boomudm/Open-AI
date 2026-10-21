"""Qdrant sharding strategy tests (issue #49)."""

from __future__ import annotations

from spark.core.config import settings
from spark.core.qdrant_strategy import collection_for, list_search_collections


def test_single_strategy_uses_base_collection(monkeypatch) -> None:
    monkeypatch.setattr(settings, "qdrant_shard_strategy", "single")
    monkeypatch.setattr(settings, "qdrant_collection", "spark_docs")
    assert collection_for("F-01", "knowledge") == "spark_docs"
    assert list_search_collections("F-01") == ["spark_docs"]


def test_per_factory_collection_name(monkeypatch) -> None:
    monkeypatch.setattr(settings, "qdrant_shard_strategy", "per_factory")
    monkeypatch.setattr(settings, "qdrant_collection", "spark_docs")
    assert collection_for("F-01") == "spark_docs__f-01"
    assert collection_for("F-02") == "spark_docs__f-02"


def test_list_search_collections_without_factory(monkeypatch) -> None:
    monkeypatch.setattr(
        "spark.core.qdrant_strategy.mandatory_factory_id_enforced",
        lambda: False,
    )
    monkeypatch.setattr(settings, "qdrant_shard_strategy", "per_factory")
    monkeypatch.setattr(settings, "qdrant_collection", "spark_docs")
    cols = list_search_collections(None)
    assert cols == ["spark_docs"]
