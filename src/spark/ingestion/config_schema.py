"""Startup validation for ingestion YAML configs (Phase 1)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from spark.core.config import settings
from spark.core.logging import get_logger
from spark.ingestion.chunk.types import CONFIG_ALLOWED_CHUNK_STRATEGIES, DEPRECATED_CHUNK_STRATEGIES
from spark.ingestion.config_loader import load_config
from spark.ingestion.constants import DEDUP_STRATEGIES

log = get_logger(__name__)

_SCHEMA_PATH = (
    Path(__file__).resolve().parents[3] / "configs" / "schemas" / "ingestion_document_type.schema.json"
)
_CHUNKING_PROFILES_PATH = Path(__file__).resolve().parents[3] / "configs" / "chunking_profiles.yaml"

# excel_parser uses table_row profile internally — not routed through ChunkStrategy registry.
EXCEL_ONLY_CHUNK_PROFILES: frozenset[str] = frozenset({"table_row"})


class IngestionConfigSchemaError(ValueError):
    """Invalid ingestion document-type YAML."""


def _load_chunk_profile_names() -> frozenset[str]:
    if not _CHUNKING_PROFILES_PATH.is_file():
        raise IngestionConfigSchemaError(f"Missing chunking profiles: {_CHUNKING_PROFILES_PATH}")
    data = yaml.safe_load(_CHUNKING_PROFILES_PATH.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise IngestionConfigSchemaError("chunking_profiles.yaml must be a mapping")
    names = {key for key in data if key != "schema_version" and isinstance(key, str)}
    if not names:
        raise IngestionConfigSchemaError("chunking_profiles.yaml defines no profiles")
    return frozenset(names)


def _validate_required_fields(document_type: str, cfg: dict[str, Any]) -> None:
    for key in ("document_type", "parser", "default_route"):
        if not cfg.get(key):
            raise IngestionConfigSchemaError(f"{document_type}: missing required field {key!r}")
    route = str(cfg.get("default_route")).lower()
    if route not in {"qdrant", "postgres", "both"}:
        raise IngestionConfigSchemaError(f"{document_type}: invalid default_route {route!r}")


def _validate_dedup(document_type: str, cfg: dict[str, Any]) -> None:
    dedup = cfg.get("dedup")
    if not dedup:
        return
    if not isinstance(dedup, dict):
        raise IngestionConfigSchemaError(f"{document_type}: dedup must be a mapping")
    strategy = str(dedup.get("strategy") or "").lower()
    if not strategy:
        raise IngestionConfigSchemaError(f"{document_type}: dedup.strategy is required when dedup is set")
    if strategy not in DEDUP_STRATEGIES:
        raise IngestionConfigSchemaError(
            f"{document_type}: unknown dedup.strategy {strategy!r} "
            f"(allowed: {sorted(DEDUP_STRATEGIES)})"
        )


def _validate_chunking(document_type: str, cfg: dict[str, Any], profiles: frozenset[str]) -> None:
    chunking = cfg.get("chunking")
    if not chunking:
        return
    if not isinstance(chunking, dict):
        raise IngestionConfigSchemaError(f"{document_type}: chunking must be a mapping")
    profile = chunking.get("profile")
    if profile is not None and str(profile) not in profiles:
        raise IngestionConfigSchemaError(
            f"{document_type}: unknown chunking.profile {profile!r} "
            f"(defined in chunking_profiles.yaml: {sorted(profiles)})"
        )
    strategy = chunking.get("strategy")
    if strategy is not None:
        normalized = str(strategy).lower()
        if normalized in DEPRECATED_CHUNK_STRATEGIES:
            raise IngestionConfigSchemaError(
                f"{document_type}: deprecated chunking.strategy {normalized!r} — "
                "use page_aware_parent_child, structure_aware, semantic_heading, or table_row"
            )
        if normalized not in CONFIG_ALLOWED_CHUNK_STRATEGIES:
            raise IngestionConfigSchemaError(
                f"{document_type}: unknown chunking.strategy {normalized!r} "
                f"(allowed: {sorted(CONFIG_ALLOWED_CHUNK_STRATEGIES)})"
            )
        threshold = chunking.get("semantic_breakpoint_threshold")
        uses_semantic_embed = normalized == "semantic_embedding" or (
            normalized == "semantic" and threshold is not None
        )
        if uses_semantic_embed and not chunking.get("offline_only"):
            raise IngestionConfigSchemaError(
                f"{document_type}: semantic embedding chunking requires chunking.offline_only=true "
                "(benchmark/offline only — not allowed on ingest hot path)"
            )


def _validate_postgres_table(document_type: str, cfg: dict[str, Any]) -> None:
    pg = cfg.get("postgres") or {}
    if pg.get("registry_only"):
        return
    table = pg.get("table")
    if not table:
        return
    from spark.ingestion.index.postgres_writer import ALLOWED_POSTGRES_TABLES

    if table not in ALLOWED_POSTGRES_TABLES:
        raise IngestionConfigSchemaError(
            f"{document_type}: postgres.table {table!r} not in allowlist {sorted(ALLOWED_POSTGRES_TABLES)}"
        )


def validate_document_type_config(document_type: str, cfg: dict[str, Any] | None = None) -> None:
    """Validate one document-type config; loads from disk when cfg is omitted."""
    data = cfg if cfg is not None else load_config(document_type)
    if not isinstance(data, dict):
        raise IngestionConfigSchemaError(f"{document_type}: config must be a mapping")
    profiles = _load_chunk_profile_names()
    _validate_required_fields(document_type, data)
    _validate_dedup(document_type, data)
    _validate_chunking(document_type, data, profiles)
    _validate_postgres_table(document_type, data)


def validate_all_ingestion_configs(*, config_dir: Path | None = None) -> list[str]:
    """Validate every ingestion YAML. Returns document types validated."""
    root = config_dir or settings.config_dir
    if not root.is_dir():
        raise IngestionConfigSchemaError(f"Ingestion config directory not found: {root}")

    doc_types = sorted(p.stem for p in root.glob("*.yaml"))
    if not doc_types:
        raise IngestionConfigSchemaError(f"No ingestion configs in {root}")

    profiles = _load_chunk_profile_names()
    for document_type in doc_types:
        cfg_path = root / f"{document_type}.yaml"
        data = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
        if not isinstance(data, dict):
            raise IngestionConfigSchemaError(f"{document_type}: config must be a mapping")
        data.setdefault("document_type", document_type)
        _validate_required_fields(document_type, data)
        _validate_dedup(document_type, data)
        _validate_chunking(document_type, data, profiles)
        _validate_postgres_table(document_type, data)
    return doc_types


def validate_ingestion_configs_at_startup() -> None:
    """Fail fast on invalid ingestion YAML before serving traffic."""
    try:
        doc_types = validate_all_ingestion_configs()
    except IngestionConfigSchemaError as exc:
        raise RuntimeError(f"Ingestion config validation failed: {exc}") from exc
    log.info(
        "ingestion_configs_validated",
        count=len(doc_types),
        schema=str(_SCHEMA_PATH.name),
    )


def load_json_schema() -> dict[str, Any]:
    """Load JSON Schema document for tooling/tests."""
    return json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
