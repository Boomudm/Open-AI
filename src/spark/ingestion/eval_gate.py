"""Runtime ingest swap eval gate — block breaking index changes without signed eval token (Phase 13)."""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from spark.core.config import settings
from spark.core.logging import get_logger
from spark.db.models.docs import Document, DocumentChunk
from spark.ingestion.context import IngestContext
from spark.ingestion.embed_lineage import CHUNK_SCHEMA_VERSION
from spark.ingestion.embed_profile import EmbedProfile
from spark.ingestion.errors import PermanentIngestError
from spark.ingestion.eval_token import verify_eval_payload
from spark.ingestion.index.sparse.encoder import SparseEncoderFactory
from spark.services.qa_cache_service import load_ingest_policy_version

log = get_logger(__name__)

EVAL_TOKEN_PREFIX = "spark:ingest:eval_token"


@dataclass(frozen=True)
class BreakingChangeSnapshot:
    embed_model_id: str
    sparse_encoder_id: str
    chunk_schema_version: int
    ingest_policy_version: str

    def config_hash(self) -> str:
        body = {
            "embed_model_id": self.embed_model_id,
            "sparse_encoder_id": self.sparse_encoder_id,
            "chunk_schema_version": self.chunk_schema_version,
            "ingest_policy_version": self.ingest_policy_version,
        }
        canonical = json.dumps(body, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def current_breaking_snapshot() -> BreakingChangeSnapshot:
    profile = EmbedProfile.from_runtime()
    sparse = SparseEncoderFactory.from_settings()
    return BreakingChangeSnapshot(
        embed_model_id=profile.model_id,
        sparse_encoder_id=sparse.encoder_id,
        chunk_schema_version=CHUNK_SCHEMA_VERSION,
        ingest_policy_version=load_ingest_policy_version(),
    )


def _eval_gate_enabled() -> bool:
    if settings.spark_testing or settings.spark_profile.strip().lower() == "test":
        return False
    return True


async def _prior_snapshot(
    session: AsyncSession,
    *,
    doc_id: uuid.UUID,
    active_generation: int,
) -> BreakingChangeSnapshot | None:
    row = (
        await session.execute(
            select(DocumentChunk.embed_model, DocumentChunk.chunk_schema_version, DocumentChunk.payload)
            .where(
                DocumentChunk.doc_id == doc_id,
                DocumentChunk.ingest_generation == active_generation,
            )
            .limit(1)
        )
    ).first()
    if not row:
        return None
    embed_model, chunk_schema, payload = row
    payload_dict = dict(payload or {})
    doc = await session.get(Document, doc_id)
    policy_version = (doc.policy_scan_version if doc else None) or ""
    return BreakingChangeSnapshot(
        embed_model_id=str(embed_model or ""),
        sparse_encoder_id=str(payload_dict.get("sparse_encoder_id") or ""),
        chunk_schema_version=int(chunk_schema or CHUNK_SCHEMA_VERSION),
        ingest_policy_version=str(policy_version),
    )


def _canonical_model_id(model_id: str) -> str:
    """Canonicalize an embed model id for equivalence comparison.

    The same weights are referenced by different labels depending on the serving
    path — e.g. the local sidecar reports ``BAAI/bge-m3`` while the remote Forge
    profile reports ``bge-m3``. Both yield byte-identical vectors (verified
    cosine == 1.0), so the org prefix and case must not read as a breaking
    change that forces re-embedding of every pre-existing document.
    """
    return model_id.strip().rsplit("/", 1)[-1].lower()


def breaking_change_detected(
    prior: BreakingChangeSnapshot | None,
    current: BreakingChangeSnapshot,
) -> bool:
    if prior is None:
        return False
    return (
        _canonical_model_id(prior.embed_model_id) != _canonical_model_id(current.embed_model_id)
        or prior.sparse_encoder_id != current.sparse_encoder_id
        or prior.chunk_schema_version != current.chunk_schema_version
        or prior.ingest_policy_version != current.ingest_policy_version
    )


def _validate_cached_token(data: dict[str, Any]) -> dict[str, Any] | None:
    if "signature" in data and "payload" in data:
        try:
            return verify_eval_payload(data)
        except ValueError as exc:
            log.warning("eval_token_invalid", error=str(exc)[:200])
            return None
    log.warning("eval_token_unsigned_or_legacy")
    return None


async def fetch_eval_token(factory_id: str | None, config_hash: str) -> dict[str, Any] | None:
    from spark.core.cache import Cache

    scope = factory_id or "global"
    key = f"{EVAL_TOKEN_PREFIX}:{scope}:{config_hash}"
    # Cache.get is the singleton accessor — the instance API is get_json/set_json
    # (Cache has no raw .get(key); calling it resolved back to the classmethod
    # and crashed every reingest at the finalize stage).
    data = await Cache.get().get_json(key)
    if not isinstance(data, dict):
        return None
    return _validate_cached_token(data)


async def store_eval_token(
    *,
    factory_id: str | None,
    config_hash: str,
    signed_token: dict[str, Any],
    ttl_sec: int = 86_400,
) -> None:
    from spark.core.cache import Cache

    scope = factory_id or "global"
    key = f"{EVAL_TOKEN_PREFIX}:{scope}:{config_hash}"
    await Cache.get().set_json(key, signed_token, ttl=ttl_sec)
    payload = signed_token.get("payload") or {}
    log.info(
        "eval_token_issued",
        factory_id=scope,
        config_hash=config_hash[:16],
        report_sha256=str(payload.get("report_sha256", ""))[:16],
        ttl_sec=ttl_sec,
    )
    from spark.audit.worm_sink import schedule_worm_audit

    schedule_worm_audit(
        "eval_token_issued",
        factory_id=scope if scope != "global" else None,
        payload={
            "config_hash": config_hash,
            "report_sha256": payload.get("report_sha256"),
            "lock_version": payload.get("lock_version"),
            "issued_by": payload.get("issued_by"),
            "expires_at": payload.get("expires_at"),
        },
    )


async def require_swap_eval_token(ctx: IngestContext, session: AsyncSession) -> None:
    """Raise when a breaking index config change lacks a valid eval pass token."""
    if not _eval_gate_enabled():
        return
    if not ctx.is_reingest:
        return

    doc = await session.get(Document, ctx.doc_id)
    if not doc or int(doc.chunks_count or 0) <= 0:
        return

    current = current_breaking_snapshot()
    prior = await _prior_snapshot(
        session,
        doc_id=ctx.doc_id,
        active_generation=int(doc.active_ingest_generation or 1),
    )
    if not breaking_change_detected(prior, current):
        return

    config_hash = current.config_hash()
    token = await fetch_eval_token(ctx.factory_id, config_hash)
    if token:
        log.info(
            "eval_gate_passed",
            doc_id=str(ctx.doc_id),
            factory_id=ctx.factory_id,
            config_hash=config_hash[:16],
            report_sha256=str(token.get("report_sha256", ""))[:16],
        )
        return

    log.error(
        "eval_gate_blocked",
        doc_id=str(ctx.doc_id),
        factory_id=ctx.factory_id,
        config_hash=config_hash[:16],
        prior=prior.__dict__ if prior else None,
        current=current.__dict__,
    )
    raise PermanentIngestError(
        "eval_gate_blocked",
        "breaking index config change requires signed eval token — run scripts/issue_eval_token.py",
    )
