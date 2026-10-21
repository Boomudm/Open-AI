"""Compliance export RBAC, rate limits, and classification filters (Phase 14)."""

from __future__ import annotations

import hashlib
import hmac
import os
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException, status

from spark.api.platform.rate_limit_lua import increment_sliding_window
from spark.compliance.taxonomy import document_type_entry, export_settings
from spark.core.security import Principal


def can_export_compliance(p: Principal) -> bool:
    allowed = export_settings().get("allowed_roles") or ["compliance_officer", "admin"]
    role_set = {str(role) for role in allowed}
    return p.is_admin or bool(role_set.intersection(set(p.roles)))


def enforce_compliance_export(p: Principal) -> None:
    if not can_export_compliance(p):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "compliance_officer role required for audit export",
        )


async def check_export_rate_limit(user_id: str) -> None:
    limit = int(export_settings().get("rate_limit_per_user_hour") or 10)
    if limit <= 0:
        return
    used = await increment_sliding_window(
        f"spark:export:rate:{user_id}",
        window_sec=3600,
    )
    if used > limit:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "audit export rate limit exceeded — try again later",
            headers={"Retry-After": "3600"},
        )


def export_download_expires_at() -> datetime:
    ttl = int(export_settings().get("download_url_ttl_sec") or 900)
    return datetime.now(tz=UTC) + timedelta(seconds=max(60, ttl))


def _export_hmac_secret() -> bytes:
    secret = os.environ.get("AUDIT_EXPORT_HMAC_SECRET") or os.environ.get("EVAL_TOKEN_HMAC_SECRET")
    if not secret:
        from spark.core.config import settings

        if settings.is_production:
            raise RuntimeError(
                "AUDIT_EXPORT_HMAC_SECRET (or EVAL_TOKEN_HMAC_SECRET) is required when APP_ENV=production"
            )
        secret = "dev-audit-export-secret"
    return secret.encode("utf-8")


def sign_export_download_token(*, user_id: str, factory_id: str | None, days: int) -> str:
    secret = _export_hmac_secret()
    expires = export_download_expires_at().isoformat()
    body = f"{user_id}|{factory_id or ''}|{days}|{expires}"
    signature = hmac.new(secret, body.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{signature[:32]}.{expires}"


def filter_worm_events_by_classification(
    events: list[dict[str, Any]],
    *,
    classification_level: str | None,
) -> list[dict[str, Any]]:
    if not classification_level:
        return events
    from spark.compliance.taxonomy import document_types_for_level

    allowed_types = document_types_for_level(classification_level)
    filtered: list[dict[str, Any]] = []
    for event in events:
        payload = event.get("payload") or {}
        doc_type = payload.get("document_type")
        if doc_type is None or str(doc_type) in allowed_types:
            filtered.append(event)
    return filtered


def redact_retrieval_row(row: dict[str, Any]) -> dict[str, Any]:
    doc_type = row.get("document_type")
    entry = document_type_entry(str(doc_type) if doc_type else None)
    if entry.get("export_allowed", True):
        return row
    redacted = dict(row)
    redacted["question"] = "[redacted — export_restricted document type]"
    redacted["export_redacted"] = True
    return redacted
