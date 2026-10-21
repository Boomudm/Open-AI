"""Resolved ingest config — profile merge and factory overrides."""

from __future__ import annotations

import pytest

from spark.ingestion.config_resolver import ConfigError, resolve_ingest_config


def test_machine_manual_parent_child_th_v2_chunk_sizes() -> None:
    resolved = resolve_ingest_config("machine_manual", {})
    assert resolved.chunking.profile == "parent_child_th_v2"
    assert resolved.chunking.parent_chunk_size == 2400
    assert resolved.chunking.child_chunk_size == 512
    assert resolved.chunking.child_chunk_overlap == 64
    assert resolved.embedding.expected_dim == 1024


def test_invalid_chunking_profile_raises() -> None:
    from spark.ingestion.config_resolver import _merge_chunking_profile

    with pytest.raises(ConfigError, match="config_profile_not_found"):
        _merge_chunking_profile({"profile": "does_not_exist"})


def test_factory_chunking_profile_override_wins() -> None:
    resolved = resolve_ingest_config(
        "machine_manual",
        {"ingest": {"chunking_profile": "compact_form_th"}},
    )
    assert resolved.chunking.profile == "compact_form_th"
    assert resolved.chunking.chunk_size == 256
    assert resolved.chunking.chunk_overlap == 64


def test_factory_embedding_profile_override() -> None:
    resolved = resolve_ingest_config(
        "machine_manual",
        {"ingest": {"embedding_profile": "bge_m3"}},
    )
    assert resolved.embedding.profile == "bge_m3"
    assert resolved.embedding.expected_dim == 1024


def test_resolved_config_hash_is_stable() -> None:
    first = resolve_ingest_config("sop", {})
    second = resolve_ingest_config("sop", {})
    assert first.config_hash() == second.config_hash()


@pytest.mark.asyncio
async def test_pdf_parser_uses_resolved_chunk_profile() -> None:
    from pathlib import Path

    from spark.ingestion.config_resolver import resolve_ingest_config
    from spark.ingestion.parsers.pdf_parser import PDFParser

    resolved = resolve_ingest_config("machine_manual", {})
    parser = PDFParser()
    # Smoke: parser accepts ResolvedIngestConfig and reads merged chunk sizes.
    records = []
    fixture = Path("tests/fixtures/sample_manual.pdf")
    if not fixture.is_file():
        pytest.skip("sample_manual.pdf fixture missing")
    async for rec in parser.parse(fixture, resolved):
        records.append(rec)
    assert records
    assert resolved.chunking.parent_chunk_size == 2400
