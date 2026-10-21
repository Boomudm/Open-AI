"""Startup validation for ingest payload contract alignment (Phase 4)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from spark.contracts.rag_payload_contract import (
    QDRANT_PAYLOAD_FIELDS,
    REQUIRED_PARSER_FIELDS_BY_CHUNKING_STRATEGY,
    required_parser_fields_for_strategy,
)
from spark.core.config import settings
from spark.core.logging import get_logger
from spark.ingestion.config_schema import IngestionConfigSchemaError, validate_all_ingestion_configs
from spark.ingestion.trust.rules_injection import validate_injection_patterns
from spark.ingestion.trust.scanner import load_content_policy

log = get_logger(__name__)


class IngestConfigValidatorError(RuntimeError):
    """Invalid ingest configuration for payload contract enforcement."""


def _validate_no_payload_whitelists(document_type: str, cfg: dict[str, Any]) -> None:
    qdrant = cfg.get("qdrant") or {}
    if not isinstance(qdrant, dict):
        return
    if qdrant.get("payload_fields"):
        raise IngestConfigValidatorError(
            f"{document_type}: qdrant.payload_fields whitelist is forbidden — "
            "remove it or use qdrant.payload_field_exclusions denylist"
        )


def _validate_chunking_strategy_fields(document_type: str, cfg: dict[str, Any]) -> None:
    chunking = cfg.get("chunking") or {}
    if not isinstance(chunking, dict):
        return
    strategy = chunking.get("strategy")
    if strategy is None:
        return
    normalized = str(strategy).strip().lower()
    if normalized not in REQUIRED_PARSER_FIELDS_BY_CHUNKING_STRATEGY:
        return
    required = required_parser_fields_for_strategy(normalized)
    unknown = required - QDRANT_PAYLOAD_FIELDS - {
        "parent_content",
        "page_content",
        "page",
        "parent_chunk_id",
        "chunk_level",
        "source_sheet",
        "row_number",
        "section_path",
    }
    if unknown:
        raise IngestConfigValidatorError(
            f"{document_type}: chunking strategy {normalized!r} requires unknown fields {sorted(unknown)}"
        )


def validate_trust_policy_schema() -> None:
    policy = load_content_policy()
    rules = policy.get("rules") or {}
    if not isinstance(rules, dict):
        raise IngestConfigValidatorError("ingest content policy rules must be a mapping")
    validate_injection_patterns(list(rules.get("injection_patterns") or []))
    validate_injection_patterns(list(rules.get("safety_critical_phrases") or []))


def validate_ingest_payload_contracts(*, config_dir: Path | None = None) -> None:
    """Validate ingestion YAML + trust policy against payload contract."""
    root = config_dir or settings.config_dir
    for path in sorted(root.glob("*.yaml")):
        document_type = path.stem
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(data, dict):
            raise IngestConfigValidatorError(f"{document_type}: config must be a mapping")
        _validate_no_payload_whitelists(document_type, data)
        _validate_chunking_strategy_fields(document_type, data)
    validate_trust_policy_schema()


def validate_ingest_contracts_at_startup() -> None:
    """Fail fast before serving traffic."""
    try:
        doc_types = validate_all_ingestion_configs()
        validate_ingest_payload_contracts()
    except (IngestionConfigSchemaError, IngestConfigValidatorError) as exc:
        raise RuntimeError(f"Ingest contract validation failed: {exc}") from exc
    log.info("ingest_payload_contracts_validated", document_types=len(doc_types))
