"""Phase 6 — single canonical chunk strategy registry."""

from __future__ import annotations

import pytest

from spark.ingestion.chunk.strategies import get_chunking_strategy, normalize_chunk_strategy
from spark.ingestion.chunk.types import (
    CANONICAL_CHUNK_STRATEGIES,
    CONFIG_ALLOWED_CHUNK_STRATEGIES,
    DEPRECATED_CHUNK_STRATEGIES,
)
from spark.ingestion.config_schema import IngestionConfigSchemaError, _validate_chunking


def test_canonical_strategies_resolve_via_factory() -> None:
    for name in sorted(CANONICAL_CHUNK_STRATEGIES):
        strategy = get_chunking_strategy(name)
        assert strategy is not None


def test_deprecated_strategy_aliases_normalize_at_runtime() -> None:
    assert normalize_chunk_strategy("parent_child") == "page_aware_parent_child"
    assert normalize_chunk_strategy("structure") == "structure_aware"
    assert normalize_chunk_strategy("semantic") == "semantic_heading"
    assert normalize_chunk_strategy("per_row") == "table_row"


def test_config_validator_rejects_deprecated_parent_child() -> None:
    profiles = frozenset({"recursive_th"})
    cfg = {
        "chunking": {
            "profile": "recursive_th",
            "strategy": "parent_child",
        }
    }
    with pytest.raises(IngestionConfigSchemaError, match="deprecated"):
        _validate_chunking("sop", cfg, profiles)


def test_config_validator_rejects_unknown_strategy() -> None:
    profiles = frozenset({"recursive_th"})
    cfg = {"chunking": {"strategy": "not_a_real_strategy"}}
    with pytest.raises(IngestionConfigSchemaError, match="unknown chunking.strategy"):
        _validate_chunking("sop", cfg, profiles)


def test_config_validator_accepts_sop_procedure() -> None:
    profiles = frozenset({"sop_procedure_th"})
    cfg = {"chunking": {"profile": "sop_procedure_th", "strategy": "sop_procedure"}}
    _validate_chunking("sop", cfg, profiles)
    assert "sop_procedure" in CONFIG_ALLOWED_CHUNK_STRATEGIES
    assert "parent_child" in DEPRECATED_CHUNK_STRATEGIES
