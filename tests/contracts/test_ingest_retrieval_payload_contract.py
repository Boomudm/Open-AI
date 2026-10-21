"""Contract tests: ingest payload ↔ Qdrant filter ↔ Postgres mirror."""

from __future__ import annotations

from pathlib import Path

import pytest

from spark.contracts.rag_payload_contract import (
    POSTGRES_MIRROR_DIMENSIONS,
    QDRANT_FILTER_DIMENSIONS,
    QDRANT_ONLY_FILTER_DIMENSIONS,
    QDRANT_PAYLOAD_FIELDS,
    QDRANT_RUNTIME_ENRICHMENT_FIELDS,
    RETRIEVAL_RUNTIME_PAYLOAD_FIELDS,
    extract_postgres_mirror_filter_keys,
    extract_qdrant_filter_keys,
    extract_qdrant_router_payload_keys,
    render_contract_markdown,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CONTRACT_DOC = _REPO_ROOT / "docs" / "internal" / "rag_payload_contract.md"


def test_qdrant_router_payload_matches_canonical_contract() -> None:
    router_keys = extract_qdrant_router_payload_keys()
    missing_from_contract = router_keys - QDRANT_PAYLOAD_FIELDS
    assert not missing_from_contract, (
        f"base_payload keys missing from contract: {sorted(missing_from_contract)}"
    )
    enrichment_only = QDRANT_PAYLOAD_FIELDS - router_keys
    assert enrichment_only <= QDRANT_RUNTIME_ENRICHMENT_FIELDS, (
        f"Unexpected contract-only payload fields: {sorted(enrichment_only - QDRANT_RUNTIME_ENRICHMENT_FIELDS)}"
    )


def test_qdrant_filter_dimensions_are_subset_of_ingest_payload() -> None:
    missing = QDRANT_FILTER_DIMENSIONS - QDRANT_PAYLOAD_FIELDS
    assert not missing, f"Filter dimensions missing from ingest payload: {sorted(missing)}"


def test_qdrant_filter_builder_matches_canonical_contract() -> None:
    source_keys = extract_qdrant_filter_keys()
    assert source_keys == QDRANT_FILTER_DIMENSIONS


def test_postgres_mirror_matches_canonical_contract() -> None:
    source_keys = extract_postgres_mirror_filter_keys()
    assert source_keys == POSTGRES_MIRROR_DIMENSIONS


def test_postgres_mirror_covers_qdrant_filter_dimensions() -> None:
    qdrant_only = (
        QDRANT_FILTER_DIMENSIONS - POSTGRES_MIRROR_DIMENSIONS - QDRANT_ONLY_FILTER_DIMENSIONS
    )
    assert not qdrant_only, f"Postgres mirror missing Qdrant filter dims: {sorted(qdrant_only)}"


def test_postgres_mirror_ingest_generation_guard() -> None:
    assert "ingest_generation" in POSTGRES_MIRROR_DIMENSIONS


def test_retrieval_runtime_fields_not_required_at_ingest() -> None:
    overlap = RETRIEVAL_RUNTIME_PAYLOAD_FIELDS & QDRANT_PAYLOAD_FIELDS
    assert not overlap


def test_contract_markdown_is_current() -> None:
    expected = render_contract_markdown()
    if not _CONTRACT_DOC.is_file():
        pytest.fail(f"Missing contract doc: {_CONTRACT_DOC}")
    assert _CONTRACT_DOC.read_text(encoding="utf-8") == expected, (
        "docs/internal/rag_payload_contract.md is stale — regenerate from "
        "render_contract_markdown()"
    )
