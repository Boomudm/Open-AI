"""Shared stage helpers."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from spark.core.logging import get_logger
from spark.core.qdrant_strategy import collection_for, get_strategy
from spark.db.models.ingestion import IngestionError
from spark.ingestion.config_resolver import ResolvedIngestConfig
from spark.ingestion.parsers.base import ParsedRecord
from spark.services.alias_resolver import AliasResolver

log = get_logger(__name__)


def expects_qdrant_output(config: ResolvedIngestConfig | dict[str, Any]) -> bool:
    if isinstance(config, ResolvedIngestConfig):
        return config.expects_qdrant_output()
    default_route = config.get("default_route")
    if default_route is None:
        return True
    return default_route in ("qdrant", "both")


def config_raw(config: ResolvedIngestConfig | dict[str, Any]) -> dict[str, Any]:
    if isinstance(config, ResolvedIngestConfig):
        return config.raw
    return config


def qdrant_collection(config: ResolvedIngestConfig | dict[str, Any], document_context: dict[str, Any]) -> str:
    raw = config_raw(config)
    qdrant_cfg = raw.get("qdrant") or {}
    if get_strategy() == "single":
        return qdrant_cfg.get("collection") or collection_for(
            document_context.get("factory_id"),
            document_context.get("document_category"),
        )
    return collection_for(
        document_context.get("factory_id"),
        document_context.get("document_category"),
    )


def empty_index_failure(
    config: dict[str, Any],
    *,
    rows_total: int,
    chunks_written: int,
) -> tuple[str, str] | None:
    if not expects_qdrant_output(config) or chunks_written > 0:
        return None
    if rows_total == 0:
        return (
            "no_extractable_text",
            "No extractable records were produced; file may be scanned, image-only, empty, or unsupported",
        )
    return (
        "no_indexable_chunks",
        "Records were parsed, but no chunks were written to the vector store",
    )


def resolve_job_status(rows_ok: int, rows_skipped: int, rows_skipped_ocr: int) -> str:
    """Partial only when indexable rows both succeeded and failed/skipped."""
    effective_skipped = max(0, rows_skipped - rows_skipped_ocr)
    if rows_ok > 0 and effective_skipped > 0:
        return "partial"
    if rows_ok > 0:
        return "completed"
    if rows_skipped > 0:
        return "partial"
    return "completed"


async def log_skip(
    session: AsyncSession,
    job_id: uuid.UUID,
    record: ParsedRecord | None,
    reason_code: str,
    reason_detail: str | None,
) -> None:
    session.add(
        IngestionError(
            job_id=job_id,
            row_number=(record.payload.get("row_number") if record else None),
            chunk_index=(record.payload.get("chunk_index") if record else None),
            reason_code=reason_code,
            reason_detail=reason_detail,
            raw_payload=(record.payload if record else None),
        )
    )


async def apply_alias_resolution(
    record: ParsedRecord,
    config: dict[str, Any],
    resolver: AliasResolver,
    session: AsyncSession,
    *,
    job_id: uuid.UUID,
) -> tuple[bool, str | None, str | None]:
    rules = config.get("resolve_aliases") or []
    for rule in rules:
        src_field = rule["field"]
        target = rule.get("target", src_field)
        on_fail = rule.get("on_fail", "skip")
        via = rule.get("via")
        raw = record.payload.get(src_field)
        if raw is None:
            continue

        resolved: str | None = None
        if via == "machine_alias_resolver":
            resolved = await resolver.resolve_machine(raw, session)

        if resolved:
            record.payload[target] = resolved
        elif on_fail == "warn":
            log.warning("alias_not_resolved", field=src_field, raw=raw)
            record.payload[f"{src_field}_unresolved"] = raw
            await log_skip(session, job_id, record, "alias_warn", f"{src_field}={raw!r}")
        elif on_fail in {"error", "skip"}:
            return False, "alias_not_resolved", f"{src_field}={raw!r}"
    return True, None, None


def document_registry_updates(
    document_context: dict[str, Any],
    chunks_count: int,
    rows_skipped: int,
    rows_skipped_ocr: int,
    *,
    trust_state: Any | None = None,
) -> dict[str, Any]:
    effective_skipped = max(0, rows_skipped - rows_skipped_ocr)
    updates: dict[str, Any] = {
        "ingest_status": "completed" if effective_skipped == 0 else "partial",
        "chunks_count": chunks_count,
        "retrieval_enabled": True,
    }
    if trust_state and trust_state.version:
        updates["policy_scan_version"] = trust_state.version
        if trust_state.max_risk_score > 0:
            updates["content_risk_score"] = trust_state.max_risk_score
    for ctx_key in ("revision", "source_file", "title"):
        if document_context.get(ctx_key) is not None:
            updates[ctx_key] = document_context[ctx_key]
    if document_context.get("page_count") is not None:
        updates["page_count"] = document_context["page_count"]
    raw_extra_metadata = document_context.get("extra_metadata")
    extra_metadata = dict(raw_extra_metadata) if isinstance(raw_extra_metadata, dict) else {}
    for key in ("ocr_page_count", "ocr_char_count", "ocr_confidence_min"):
        if document_context.get(key) is not None:
            extra_metadata[key] = document_context[key]
    if rows_skipped_ocr:
        extra_metadata["rows_skipped_ocr"] = rows_skipped_ocr
    if trust_state and trust_state.findings:
        updates["policy_findings_json"] = trust_state.findings[:50]
        extra_metadata["policy_findings"] = trust_state.findings[:50]
    if extra_metadata:
        updates["extra_metadata"] = extra_metadata
    return updates


def quarantine_registry_updates(
    document_context: dict[str, Any],
    *,
    trust_result: Any,
    artifact_uri: str,
) -> dict[str, Any]:
    updates: dict[str, Any] = {
        "ingest_status": "quarantined",
        "chunks_count": 0,
        "retrieval_enabled": False,
        "quarantine_reason": "content_policy_quarantine",
        "policy_scan_version": trust_result.policy_version,
        "content_risk_score": trust_result.risk_score,
        "policy_findings_json": trust_result.findings_summary()[:50],
        "quarantine_artifact_uri": artifact_uri,
    }
    for ctx_key in ("revision", "source_file", "title"):
        if document_context.get(ctx_key) is not None:
            updates[ctx_key] = document_context[ctx_key]
    if document_context.get("page_count") is not None:
        updates["page_count"] = document_context["page_count"]
    return updates
