"""Extended RAG payload contract tests (Phase 4)."""

from __future__ import annotations

from spark.contracts.rag_payload_contract import (
    PARSER_PG_ONLY_FIELDS,
    QDRANT_PAYLOAD_FIELDS,
    REQUIRED_FIELDS_BY_CHUNKING_STRATEGY,
    required_parser_fields_for_strategy,
)


def test_boost_tokens_in_qdrant_contract() -> None:
    assert "boost_tokens" in QDRANT_PAYLOAD_FIELDS


def test_parent_content_is_pg_only_not_qdrant_contract_field() -> None:
    assert "parent_content" in PARSER_PG_ONLY_FIELDS
    assert "parent_content" not in QDRANT_PAYLOAD_FIELDS


def test_required_fields_by_chunking_strategy_exported() -> None:
    assert "page_aware_parent_child" in REQUIRED_FIELDS_BY_CHUNKING_STRATEGY
    assert required_parser_fields_for_strategy("page_aware_parent_child") >= {
        "parent_chunk_id",
        "parent_content",
        "page",
    }
