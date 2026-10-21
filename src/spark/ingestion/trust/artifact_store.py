"""Persist and load quarantined parse artifacts."""

from __future__ import annotations

import io
import json
from typing import Any
from uuid import UUID

from spark.core.config import settings
from spark.core.logging import get_logger
from spark.ingestion.parsers.base import ParsedRecord
from spark.storage import get_storage

log = get_logger(__name__)


def quarantine_object_key(doc_id: UUID) -> str:
    return f"documents/_quarantine/{doc_id}/artifact.json"


def quarantine_local_path(doc_id: UUID) -> str:
    return str(settings.documents_dir / "_quarantine" / str(doc_id) / "artifact.json")


def _record_to_dict(rec: ParsedRecord) -> dict[str, Any]:
    return {
        "route": rec.route,
        "payload": rec.payload,
        "text_for_embedding": rec.text_for_embedding,
    }


def _record_from_dict(data: dict[str, Any]) -> ParsedRecord:
    return ParsedRecord(
        route=str(data.get("route") or "qdrant"),
        payload=dict(data.get("payload") or {}),
        text_for_embedding=data.get("text_for_embedding"),
    )


async def save_quarantine_artifact(
    doc_id: UUID,
    *,
    records: list[ParsedRecord],
    document_context: dict[str, Any],
    policy_version: str,
    findings: list[dict[str, Any]],
    risk_score: float,
    upload_sha256: str | None = None,
) -> str:
    """Store parsed rows + policy report for later admin release indexing."""
    payload = {
        "doc_id": str(doc_id),
        "document_context": document_context,
        "policy_version": policy_version,
        "content_risk_score": risk_score,
        "findings": findings,
        "upload_sha256": upload_sha256,
        "records": [_record_to_dict(rec) for rec in records],
    }
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    storage = get_storage()
    uri = await storage.put_object(
        quarantine_object_key(doc_id),
        io.BytesIO(raw),
        content_type="application/json",
        metadata={"doc_id": str(doc_id), "kind": "quarantine_artifact"},
    )
    log.info("quarantine_artifact_saved", doc_id=str(doc_id), storage_uri=uri)
    return uri


def _load_artifact_json_from_storage(storage_uri: str) -> dict[str, Any] | None:
    """Read artifact JSON from any storage URI (file:// or s3://)."""
    storage = get_storage()
    local = storage.local_path(storage_uri)
    if local and local.is_file():
        with local.open(encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else None
    raw = b"".join(storage.open_sync(storage_uri))
    data = json.loads(raw.decode("utf-8"))
    return data if isinstance(data, dict) else None


async def load_quarantine_artifact(doc_id: UUID, *, storage_uri: str | None = None) -> dict[str, Any]:
    if storage_uri:
        data = _load_artifact_json_from_storage(storage_uri)
        if data is not None:
            return data

    path = settings.documents_dir / "_quarantine" / str(doc_id) / "artifact.json"
    if path.is_file():
        with path.open(encoding="utf-8") as handle:
            data = json.load(handle)
        if isinstance(data, dict):
            return data

    raise FileNotFoundError(f"Quarantine artifact not found for doc_id={doc_id}")


def records_from_artifact(artifact: dict[str, Any]) -> list[ParsedRecord]:
    raw_records = artifact.get("records") or []
    if not isinstance(raw_records, list):
        return []
    return [_record_from_dict(item) for item in raw_records if isinstance(item, dict)]
