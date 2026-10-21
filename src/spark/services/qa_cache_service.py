"""Opt-in verified Q&A cache with doc-based invalidation."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from spark.ingestion.embed_profile import EmbedProfile
from spark.core.config import settings
from spark.core.logging import get_logger
from spark.core.metrics import qa_cache_hit_total, qa_cache_invalidate_total
from spark.core.security import Principal
from spark.db.models.chat import ChatMessage
from spark.db.models.docs import Document, DocumentChunk
from spark.db.models.qa_cache import VerifiedQACache

log = get_logger(__name__)


def normalize_question(text: str) -> str:
    return " ".join((text or "").strip().lower().split())


def question_hash(text: str) -> str:
    return hashlib.sha256(normalize_question(text).encode()).hexdigest()


def load_intent_weight_version() -> str:
    from spark.retrieval.intent.weights import load_intent_weights_config

    return str(load_intent_weights_config().version)


def load_ingest_policy_version() -> str:
    from spark.ingestion.trust.scanner import load_content_policy

    return str(load_content_policy().get("version") or "0")


async def resolve_embed_profile_for_factory(
    db: AsyncSession,
    factory_id: str | None,
) -> EmbedProfile:
    from spark.services.factory_config_service import factory_config_service

    cfg = await factory_config_service.resolve(db, factory_id)
    return EmbedProfile.from_runtime(cfg.get("llm_profile"))


async def active_generation_hash_for_factory(db: AsyncSession, factory_id: str) -> str:
    rows = (
        await db.execute(
            select(Document.doc_id, Document.active_ingest_generation).where(
                Document.factory_id == factory_id,
                Document.retrieval_enabled.is_(True),
            )
        )
    ).all()
    pairs = sorted((str(row.doc_id), int(row.active_ingest_generation)) for row in rows)
    return hashlib.sha256(json.dumps(pairs, sort_keys=True).encode()).hexdigest()


def filter_fingerprint(
    *,
    factory_id: str | None,
    machine_id: str | None = None,
    doc_type: str | None = None,
    embed_model_id: str | None = None,
    embed_model_version: str | None = None,
    active_generation_hash: str | None = None,
    policy_version: str | None = None,
    intent_weight_version: str | int | None = None,
    chunk_snapshot_hash: str | None = None,
) -> str:
    payload = {
        "doc_type": doc_type or "",
        "factory_id": factory_id or "",
        "machine_id": machine_id or "",
        "embed_model_id": embed_model_id or "",
        "embed_model_version": embed_model_version or "",
        "active_generation_hash": active_generation_hash or "",
        "policy_version": policy_version or "",
        "intent_weight_version": str(intent_weight_version or ""),
        "chunk_snapshot_hash": chunk_snapshot_hash or "",
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


async def build_cache_fingerprint(
    db: AsyncSession,
    *,
    factory_id: str | None,
    machine_id: str | None = None,
    doc_type: str | None = None,
    sources: list[dict[str, Any]] | None = None,
) -> str:
    profile = await resolve_embed_profile_for_factory(db, factory_id)
    generation_hash = (
        await active_generation_hash_for_factory(db, factory_id)
        if factory_id
        else ""
    )
    snapshot = await chunk_snapshot_hash(db, list(sources or [])) if sources else None
    return filter_fingerprint(
        factory_id=factory_id,
        machine_id=machine_id,
        doc_type=doc_type,
        embed_model_id=profile.model_id,
        embed_model_version=profile.version,
        active_generation_hash=generation_hash,
        policy_version=load_ingest_policy_version(),
        intent_weight_version=load_intent_weight_version(),
        chunk_snapshot_hash=snapshot,
    )


async def chunk_snapshot_hash(db: AsyncSession, sources: list[dict[str, Any]]) -> str | None:
    chunk_ids: list[uuid.UUID] = []
    for src in sources:
        raw = src.get("chunk_id")
        if raw:
            try:
                chunk_ids.append(uuid.UUID(str(raw)))
            except (TypeError, ValueError):
                continue
    if not chunk_ids:
        return None
    rows = (
        await db.execute(
            select(DocumentChunk.chunk_id, DocumentChunk.ingest_generation).where(
                DocumentChunk.chunk_id.in_(chunk_ids)
            )
        )
    ).all()
    if len(rows) != len(set(chunk_ids)):
        return None
    pairs = sorted((str(row.chunk_id), int(row.ingest_generation)) for row in rows)
    return hashlib.sha256(json.dumps(pairs).encode()).hexdigest()


def embed_cache_fingerprint(*, llm_profile_name: str | None = None) -> str:
    profile = EmbedProfile.from_runtime(llm_profile_name)
    return profile.version


class QACacheService:
    async def lookup(
        self,
        db: AsyncSession,
        *,
        factory_id: str | None,
        question: str,
        principal: Principal | None,
        machine_id: str | None = None,
        doc_type: str | None = None,
    ) -> dict[str, Any] | None:
        if not factory_id or not settings.qa_cache_enabled:
            return None
        q_hash = question_hash(question)
        fp = await build_cache_fingerprint(
            db,
            factory_id=factory_id,
            machine_id=machine_id,
            doc_type=doc_type,
        )
        stmt = (
            select(VerifiedQACache)
            .where(
                VerifiedQACache.factory_id == factory_id,
                VerifiedQACache.question_hash == q_hash,
                VerifiedQACache.verification_method == "admin",
            )
            .order_by(VerifiedQACache.created_at.desc())
        )
        rows = (await db.execute(stmt)).scalars().all()
        now = datetime.now(tz=UTC)
        for row in rows:
            if row.filter_fingerprint and row.filter_fingerprint != fp:
                continue
            if row.expires_at and row.expires_at < now:
                continue
            if not await self._docs_still_valid(db, list(row.source_doc_ids or [])):
                continue
            if not await self._chunks_still_valid(db, list(row.sources or []), row.filter_fingerprint):
                continue
            if principal and not principal.is_admin and factory_id not in principal.factory_access:
                continue
            row.hit_count = int(row.hit_count or 0) + 1
            await db.flush()
            qa_cache_hit_total.inc()
            log.info("qa_cache_hit", factory_id=factory_id, cache_id=str(row.cache_id))
            return {
                "answer": row.answer_text,
                "sources": row.sources or [],
                "cache_hit": True,
                "cache_id": str(row.cache_id),
                "cache_fingerprint": fp,
                "filter_fingerprint": row.filter_fingerprint,
                "source_doc_ids": [str(item) for item in (row.source_doc_ids or [])],
            }
        return None

    async def verify_message(
        self,
        db: AsyncSession,
        *,
        message: ChatMessage,
        factory_id: str,
        question_text: str,
        principal: Principal,
        machine_id: str | None = None,
        doc_type: str | None = None,
    ) -> VerifiedQACache:
        if not principal.is_admin:
            raise PermissionError("admin required to verify answers")
        if message.role != "assistant":
            raise ValueError("only assistant messages can be verified")
        sources = list(message.sources or [])
        doc_ids: list[uuid.UUID] = []
        for src in sources:
            raw = src.get("doc_id")
            if raw:
                doc_ids.append(uuid.UUID(str(raw)))
        snapshot = await chunk_snapshot_hash(db, sources)
        profile = await resolve_embed_profile_for_factory(db, factory_id)
        if snapshot and sources:
            sources = [
                {
                    **dict(s),
                    "_cache_meta": {
                        "chunk_snapshot_hash": snapshot,
                        "embed_model_version": profile.version,
                        "embed_model_id": profile.model_id,
                    },
                }
                if idx == 0
                else dict(s)
                for idx, s in enumerate(sources)
            ]
        ttl = settings.qa_cache_ttl_days
        expires = (
            datetime.now(tz=UTC) + timedelta(days=ttl) if ttl > 0 else None
        )
        fingerprint = await build_cache_fingerprint(
            db,
            factory_id=factory_id,
            machine_id=machine_id,
            doc_type=doc_type,
            sources=sources,
        )
        entry = VerifiedQACache(
            factory_id=factory_id,
            machine_id=machine_id,
            intent="factual",
            question_text=question_text,
            question_hash=question_hash(question_text),
            filter_fingerprint=fingerprint,
            answer_text=message.content or "",
            sources=sources,
            source_doc_ids=doc_ids,
            verification_method="admin",
            verification_score=1.0,
            source_message_id=message.message_id,
            expires_at=expires,
        )
        db.add(entry)
        message.verified_at = datetime.now(tz=UTC)
        await db.flush()
        log.info("qa_cache_verified", cache_id=str(entry.cache_id), factory_id=factory_id)
        from spark.services.semantic_cache import store_question_embedding
        await store_question_embedding(db, str(entry.cache_id), question_text)
        return entry

    async def invalidate_by_doc_id(self, db: AsyncSession, doc_id: uuid.UUID) -> int:
        stmt = select(VerifiedQACache).where(
            VerifiedQACache.source_doc_ids.contains([doc_id])
        )
        rows = (await db.execute(stmt)).scalars().all()
        if not rows:
            return 0
        ids = [r.cache_id for r in rows]
        await db.execute(delete(VerifiedQACache).where(VerifiedQACache.cache_id.in_(ids)))
        qa_cache_invalidate_total.inc(len(rows))
        log.info("qa_cache_invalidated", doc_id=str(doc_id), count=len(rows))
        return len(rows)

    async def _chunks_still_valid(
        self,
        db: AsyncSession,
        sources: list[dict[str, Any]],
        fingerprint: str | None,
    ) -> bool:
        stored_hash: str | None = None
        stored_embed: str | None = None
        for src in sources:
            meta = src.get("_cache_meta") if isinstance(src, dict) else None
            if isinstance(meta, dict):
                stored_hash = meta.get("chunk_snapshot_hash") or stored_hash
                stored_embed = meta.get("embed_model_version") or stored_embed
        if stored_hash is None:
            return True
        profile = EmbedProfile.from_runtime()
        if stored_embed and stored_embed != profile.version:
            return False
        current = await chunk_snapshot_hash(db, sources)
        return current == stored_hash

    async def _docs_still_valid(self, db: AsyncSession, doc_ids: list[uuid.UUID]) -> bool:
        if not doc_ids:
            return True
        for doc_id in doc_ids:
            doc = await db.get(Document, doc_id)
            if doc is None:
                return False
            if hasattr(doc, "is_active") and doc.is_active is False:
                return False
            if hasattr(doc, "retrieval_enabled") and doc.retrieval_enabled is False:
                return False
        return True


qa_cache_service = QACacheService()
