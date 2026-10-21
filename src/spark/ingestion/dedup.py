"""Row-level dedup strategy registry (Phase 3)."""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from spark.db.models.docs import DocumentChunk
from spark.ingestion.context import IngestContext
from spark.ingestion.parsers.base import ParsedRecord

_STRATEGY_REGISTRY: dict[str, type[DedupStrategy]] = {}


@dataclass(frozen=True)
class DedupDecision:
    skip: bool
    reason: str | None = None
    is_ocr_skip: bool = False


class DedupStrategy(Protocol):
    async def should_skip(
        self,
        record: ParsedRecord,
        ctx: IngestContext,
        session: AsyncSession,
        *,
        seen_chunk_hashes: set[str] | None = None,
    ) -> DedupDecision: ...


def register(name: str):
    def decorator(cls: type[DedupStrategy]) -> type[DedupStrategy]:
        _STRATEGY_REGISTRY[name.lower()] = cls
        return cls

    return decorator


def get_dedup_strategy(name: str | None) -> DedupStrategy | None:
    if not name:
        return None
    cls = _STRATEGY_REGISTRY.get(str(name).lower())
    return cls() if cls else None


def chunk_content_hash(text: str | None) -> str:
    normalized = (text or "").strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _dedup_keys(config: dict[str, Any]) -> list[str]:
    dedup_cfg = config.get("dedup") or {}
    raw = dedup_cfg.get("by")
    if raw is None:
        return []
    if isinstance(raw, str):
        return [raw]
    if isinstance(raw, list):
        return [str(k) for k in raw]
    return []


def _payload_value(key: str, record: ParsedRecord, ctx: IngestContext) -> Any:
    if key in record.payload:
        return record.payload.get(key)
    return ctx.document_context.get(key)


@register("reingest_replace")
class ReingestReplaceStrategy:
    """Row-level no-op: document-level replace via generation swap on re-upload."""

    async def should_skip(
        self,
        record: ParsedRecord,
        ctx: IngestContext,
        session: AsyncSession,
        *,
        seen_chunk_hashes: set[str] | None = None,
    ) -> DedupDecision:
        del record, ctx, session, seen_chunk_hashes
        return DedupDecision(skip=False)


@register("skip_if_exists")
class SkipIfExistsStrategy:
    async def should_skip(
        self,
        record: ParsedRecord,
        ctx: IngestContext,
        session: AsyncSession,
        *,
        seen_chunk_hashes: set[str] | None = None,
    ) -> DedupDecision:
        keys = _dedup_keys(ctx.config_raw)
        if not keys:
            return DedupDecision(skip=False)

        if record.payload.get("_ocr_skipped"):
            return DedupDecision(skip=True, reason="ocr_page_skipped", is_ocr_skip=True)

        if record.route in ("qdrant", "both"):
            content = record.text_for_embedding or record.payload.get("page_content") or ""
            digest = chunk_content_hash(str(content))
            if seen_chunk_hashes is not None:
                if digest in seen_chunk_hashes:
                    return DedupDecision(skip=True, reason=f"duplicate_chunk_hash={digest[:12]}")
                seen_chunk_hashes.add(digest)

            if "chunk_index" in keys or "page_content" in keys:
                generation = ctx.staging_generation if ctx.staging_generation is not None else 1
                existing_hash = await session.scalar(
                    select(DocumentChunk.chunk_id)
                    .where(
                        DocumentChunk.doc_id == ctx.doc_id,
                        DocumentChunk.ingest_generation == generation,
                        DocumentChunk.content == str(content).strip(),
                    )
                    .limit(1)
                )
                if existing_hash is not None:
                    return DedupDecision(skip=True, reason="duplicate_chunk_content")

        return DedupDecision(skip=False)


async def should_skip_row(
    record: ParsedRecord,
    config: dict[str, Any],
    session: AsyncSession,
    *,
    doc_id: uuid.UUID,
    document_context: dict[str, Any],
    seen_chunk_hashes: set[str] | None = None,
    ingest_ctx: IngestContext | None = None,
) -> tuple[bool, str | None]:
    """Backward-compatible wrapper over the dedup strategy registry."""
    dedup_cfg = config.get("dedup") or {}
    strategy_name = str(dedup_cfg.get("strategy") or "").lower()
    strategy = get_dedup_strategy(strategy_name)
    if strategy is None:
        return False, None

    ctx = ingest_ctx or IngestContext(
        doc_id=doc_id,
        job_id=uuid.uuid4(),
        factory_id=document_context.get("factory_id"),
        machine_id=document_context.get("machine_id"),
        document_type=str(document_context.get("document_type") or config.get("document_type") or ""),
        file_hash_sha256=document_context.get("file_hash_sha256"),
        document_context=document_context,
        config_raw=config,
        file_path=__import__("pathlib").Path(str(document_context.get("source_file") or "unknown")),
    )
    decision = await strategy.should_skip(record, ctx, session, seen_chunk_hashes=seen_chunk_hashes)
    return decision.skip, decision.reason


async def should_skip_row_with_meta(
    record: ParsedRecord,
    ctx: IngestContext,
    session: AsyncSession,
    *,
    seen_chunk_hashes: set[str] | None = None,
) -> DedupDecision:
    dedup_cfg = ctx.config_raw.get("dedup") or {}
    strategy_name = str(dedup_cfg.get("strategy") or "").lower()
    strategy = get_dedup_strategy(strategy_name)
    if strategy is None:
        return DedupDecision(skip=False)
    return await strategy.should_skip(record, ctx, session, seen_chunk_hashes=seen_chunk_hashes)
