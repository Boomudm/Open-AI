"""Mandatory factory_id for retrieval (remediation v2 Phase 8)."""

from __future__ import annotations

import pytest

from spark.core.config import settings
from spark.core.qdrant_strategy import (
    list_search_collections,
    mandatory_factory_id_enforced,
    validate_factory_id_for_retrieval,
)


def test_mandatory_factory_id_enforced_from_manifest() -> None:
    assert mandatory_factory_id_enforced() is True


def test_list_search_collections_without_factory_when_not_enforced(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "spark.core.qdrant_strategy.mandatory_factory_id_enforced",
        lambda: False,
    )
    monkeypatch.setattr(settings, "qdrant_shard_strategy", "per_factory")
    monkeypatch.setattr(settings, "qdrant_collection", "spark_docs")
    assert list_search_collections(None) == ["spark_docs"]


def test_list_search_collections_raises_without_factory_when_enforced(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "spark.core.qdrant_strategy.mandatory_factory_id_enforced",
        lambda: True,
    )
    monkeypatch.setattr(settings, "qdrant_shard_strategy", "per_factory")
    with pytest.raises(ValueError, match="factory_id required"):
        list_search_collections(None)


def test_validate_factory_id_for_retrieval(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "spark.core.qdrant_strategy.mandatory_factory_id_enforced",
        lambda: True,
    )
    with pytest.raises(ValueError, match="factory_id required"):
        validate_factory_id_for_retrieval(None)
    validate_factory_id_for_retrieval("F-01")
