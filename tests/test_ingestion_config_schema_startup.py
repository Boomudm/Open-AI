"""Ingestion YAML schema validation at startup."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from spark.ingestion.config_schema import (
    IngestionConfigSchemaError,
    validate_all_ingestion_configs,
    validate_document_type_config,
)


def test_validate_all_ingestion_configs_passes_repo_configs() -> None:
    doc_types = validate_all_ingestion_configs()
    assert len(doc_types) >= 10
    assert "knowledge_document" in doc_types
    assert "machine_manual" in doc_types


def test_unknown_dedup_strategy_fails(tmp_path: Path) -> None:
    cfg_dir = tmp_path / "ingestion"
    cfg_dir.mkdir()
    (cfg_dir / "bad_type.yaml").write_text(
        yaml.dump(
            {
                "document_type": "bad_type",
                "parser": "text",
                "default_route": "qdrant",
                "dedup": {"strategy": "magic_dedup", "by": "file_hash_sha256"},
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(IngestionConfigSchemaError, match="unknown dedup.strategy"):
        validate_all_ingestion_configs(config_dir=cfg_dir)


def test_unknown_chunk_profile_fails(tmp_path: Path) -> None:
    cfg_dir = tmp_path / "ingestion"
    cfg_dir.mkdir()
    (cfg_dir / "bad_type.yaml").write_text(
        yaml.dump(
            {
                "document_type": "bad_type",
                "parser": "text",
                "default_route": "qdrant",
                "chunking": {"profile": "nonexistent_profile_xyz"},
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(IngestionConfigSchemaError, match="unknown chunking.profile"):
        validate_all_ingestion_configs(config_dir=cfg_dir)


def test_reingest_replace_strategy_allowed(tmp_path: Path) -> None:
    cfg_dir = tmp_path / "ingestion"
    cfg_dir.mkdir()
    (cfg_dir / "manual.yaml").write_text(
        yaml.dump(
            {
                "document_type": "manual",
                "parser": "pdf",
                "default_route": "qdrant",
                "dedup": {"strategy": "reingest_replace", "by": "file_hash_sha256"},
            }
        ),
        encoding="utf-8",
    )
    validate_all_ingestion_configs(config_dir=cfg_dir)


def test_validate_document_type_config_unknown_strategy_inline() -> None:
    with pytest.raises(IngestionConfigSchemaError, match="unknown dedup.strategy"):
        validate_document_type_config(
            "x",
            {
                "document_type": "x",
                "parser": "text",
                "default_route": "qdrant",
                "dedup": {"strategy": "not_real"},
            },
        )
