"""Ingest pipeline entrypoint — delegates to staged runner (Phase 3)."""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import func, select, update

from spark.core.database import AsyncSessionLocal
from spark.ingestion.config_resolver import ResolvedIngestConfig
from spark.ingestion.context import IngestContext, JobSummary
from spark.ingestion.errors import IngestionFailure, PermanentIngestError, TransientIngestError
from spark.ingestion.parsers import get_parser  # noqa: F401 — tests monkeypatch this
from spark.ingestion.stages.common import (
    apply_alias_resolution as _apply_alias_resolution,
    document_registry_updates as _document_registry_updates,
    empty_index_failure as _empty_index_failure,
    expects_qdrant_output as _expects_qdrant_output,
    qdrant_collection as _qdrant_collection,
)
from spark.ingestion.stages.parse_stage import resolve_parser_name
from spark.ingestion.stages.runner import run_staged_pipeline

__all__ = [
    "IngestionFailure",
    "TransientIngestError",
    "PermanentIngestError",
    "JobSummary",
    "get_parser",
    "run_pipeline",
    "run_pipeline_sync",
    "run_index_from_artifact",
    "_document_registry_updates",
    "_empty_index_failure",
    "_apply_alias_resolution",
    "_prepare_reingest_if_needed",
    "_resolve_parser_name",
]


def _resolve_parser_name(
    config: ResolvedIngestConfig | dict[str, Any],
    file_path: Path,
    document_context: dict[str, Any],
) -> str:
    """Backward-compatible wrapper for tests and legacy imports."""
    if isinstance(config, ResolvedIngestConfig):
        resolved = config
        raw = config.raw
        doc_type = str(document_context.get("document_type") or config.document_type)
    else:
        raw = config
        doc_type = str(document_context.get("document_type") or raw.get("document_type") or "")
        resolved = None
    ctx = IngestContext(
        doc_id=uuid.uuid4(),
        job_id=uuid.uuid4(),
        factory_id=document_context.get("factory_id"),
        machine_id=document_context.get("machine_id"),
        document_type=doc_type,
        file_hash_sha256=document_context.get("file_hash_sha256"),
        document_context=document_context,
        config_raw=raw,
        resolved_config=resolved,
        file_path=file_path,
    )
    return resolve_parser_name(ctx)


async def run_pipeline(
    doc_id: uuid.UUID,
    file_path: Path,
    document_type: str,
    document_context: dict[str, Any],
    job_id: uuid.UUID | None = None,
) -> JobSummary:
    return await run_staged_pipeline(
        doc_id,
        file_path,
        document_type,
        document_context,
        job_id=job_id,
    )


async def run_index_from_artifact(
    doc_id: uuid.UUID,
    *,
    job_id: uuid.UUID | None = None,
) -> JobSummary:
    """Index a quarantined document from stored parse artifact after admin release."""
    from spark.ingestion.trust.artifact_store import load_quarantine_artifact, records_from_artifact
    from spark.ingestion.config_resolver import resolve_ingest_config
    from spark.ingestion.context import IngestContext
    from spark.ingestion.dedup import should_skip_row
    from spark.db.models.docs import DocumentChunk
    from spark.ingestion.ingest_swap import (
        IngestGenerationPlan,
        abort_staging_ingest,
        commit_ingest_swap,
        resolve_ingest_generation,
    )
    from spark.ingestion.index import PostgresRouter, QdrantRouter
    from spark.ingestion.stages.common import document_registry_updates
    from spark.ingestion.stages.index_stage import QDRANT_FLUSH_SIZE
    from spark.ingestion.validators import Validator
    from spark.db.models.docs import Document
    from spark.services.alias_resolver import AliasResolver

    async with AsyncSessionLocal() as session:
        doc = await session.get(Document, doc_id)
        if not doc:
            raise PermanentIngestError("artifact_missing", f"document {doc_id} not found")
        # "indexing" is also valid: the release endpoint sets it synchronously
        # before enqueuing this task (document_release.py line ~138).  The task
        # must therefore accept "indexing" in addition to the pre-release states.
        if doc.ingest_status not in ("quarantined", "pending_release", "indexing"):
            raise PermanentIngestError(
                "invalid_release_state",
                f"document {doc_id} is not quarantined (status={doc.ingest_status})",
            )
        artifact_uri = doc.quarantine_artifact_uri
        fallback_document_type = doc.document_type

    artifact = await load_quarantine_artifact(doc_id, storage_uri=artifact_uri)
    document_context = dict(artifact.get("document_context") or {})
    document_type = str(document_context.get("document_type") or fallback_document_type)
    parsed_records = records_from_artifact(artifact)
    if not parsed_records:
        raise PermanentIngestError("artifact_empty", "quarantine artifact has no parsed records")

    # Normalize artifact records before indexing.
    # Table leaves are atomic — they have no separate parent text — so the
    # chunk itself is its own parent.  Artifacts saved before this field was
    # required may omit these keys; filling them in here keeps the
    # required_parser_fields check from raising for page_aware_parent_child.
    # Some quarantine artifacts also carry a duplicated chunk_id across every
    # record (bug in early saves); re-derive stable per-row IDs before write.
    from spark.ingestion.chunk.stable_id import section_path_tuple, stable_chunk_id

    seen_chunk_ids: set[str] = set()
    for rec in parsed_records:
        p = rec.payload
        if p.get("block_type") == "table" or p.get("chunk_level") == "table":
            if not p.get("parent_content"):
                p["parent_content"] = p.get("page_content") or ""
            if not p.get("parent_chunk_id"):
                p["parent_chunk_id"] = p.get("chunk_id") or ""
        cid = str(p.get("chunk_id") or "")
        if not cid or cid in seen_chunk_ids:
            path = section_path_tuple(p.get("section_path"))
            leaf_index = int(p.get("chunk_index") or len(seen_chunk_ids))
            p["chunk_id"] = str(stable_chunk_id(doc_id, path, leaf_index))
        seen_chunk_ids.add(str(p["chunk_id"]))

    summary = JobSummary(job_id=job_id or uuid.uuid4(), doc_id=doc_id, status="running")
    factory_cfg: dict[str, Any] = {}
    factory_id = document_context.get("factory_id")
    if factory_id:
        from spark.services.factory_config_service import factory_config_service

        async with AsyncSessionLocal() as cfg_session:
            factory_cfg = await factory_config_service.resolve(cfg_session, str(factory_id))

    resolved = resolve_ingest_config(document_type, factory_cfg)
    ctx = IngestContext.build(
        doc_id=doc_id,
        job_id=summary.job_id,
        document_type=document_type,
        file_path=Path(document_context.get("source_file") or "artifact"),
        document_context=document_context,
        resolved=resolved,
    )
    validator = Validator()
    qdrant_router = QdrantRouter()
    postgres_router = PostgresRouter()
    alias_resolver = AliasResolver()
    qdrant_batch: list = []
    postgres_batch: list = []
    chunks_written = 0
    ingest_plan: IngestGenerationPlan | None = None
    qdrant_collection_name: str | None = None
    seen_chunk_hashes: set[str] = set()
    allocated_chunk_ids: set[uuid.UUID] = set()

    async with AsyncSessionLocal() as session:
        if _expects_qdrant_output(resolved):
            ingest_plan = await resolve_ingest_generation(session, doc_id)
            qdrant_collection_name = _qdrant_collection(resolved, document_context)
            if ingest_plan is not None:
                staging_count = await session.scalar(
                    select(func.count())
                    .select_from(DocumentChunk)
                    .where(
                        DocumentChunk.doc_id == doc_id,
                        DocumentChunk.ingest_generation == ingest_plan.staging,
                    )
                )
                if staging_count:
                    await abort_staging_ingest(
                        doc_id=doc_id,
                        plan=ingest_plan,
                        qdrant_router=qdrant_router,
                        session=session,
                        collection=qdrant_collection_name,
                    )
                    await session.commit()

        for rec in parsed_records:
            skip, _detail = await should_skip_row(
                rec,
                ctx.config_raw,
                session,
                doc_id=doc_id,
                document_context=document_context,
                seen_chunk_hashes=seen_chunk_hashes,
                ingest_ctx=ctx,
            )
            if skip:
                summary.rows_skipped += 1
                continue
            ok, _reason, _detail = await _apply_alias_resolution(
                rec, ctx.config_raw, alias_resolver, session, job_id=summary.job_id
            )
            if not ok:
                summary.rows_skipped += 1
                continue
            ok, _reason, _detail = validator.validate(rec, ctx.config_raw, document_context)
            if not ok:
                summary.rows_skipped += 1
                continue
            if rec.route in ("qdrant", "both"):
                qdrant_batch.append(rec)
            if rec.route in ("postgres", "both"):
                postgres_batch.append(rec)
            summary.rows_ok += 1
            if ingest_plan and len(qdrant_batch) >= QDRANT_FLUSH_SIZE:
                chunks_written += await qdrant_router.write(
                    qdrant_batch,
                    doc_id,
                    ctx.config_raw,
                    document_context,
                    session,
                    ingest_generation=ingest_plan.staging,
                    allocated_chunk_ids=allocated_chunk_ids,
                )
                qdrant_batch.clear()

        if qdrant_batch and ingest_plan:
            chunks_written += await qdrant_router.write(
                qdrant_batch,
                doc_id,
                ctx.config_raw,
                document_context,
                session,
                ingest_generation=ingest_plan.staging,
                allocated_chunk_ids=allocated_chunk_ids,
            )
        if postgres_batch:
            await postgres_router.write(postgres_batch, doc_id, ctx.config_raw, document_context, session)

        registry_updates = document_registry_updates(
            document_context,
            chunks_written,
            summary.rows_skipped,
            summary.rows_skipped_ocr,
        )
        registry_updates["ingest_status"] = "completed" if summary.rows_skipped == 0 else "partial"
        registry_updates["retrieval_enabled"] = True
        registry_updates["quarantine_reason"] = None

        if ingest_plan is not None and _expects_qdrant_output(resolved):
            saga = await commit_ingest_swap(
                doc_id=doc_id,
                plan=ingest_plan,
                chunks_count=chunks_written,
                document_updates=registry_updates,
                qdrant_router=qdrant_router,
                session=session,
                collection=qdrant_collection_name,
                reason_code="released_from_quarantine",
                factory_id=str(factory_id) if factory_id else None,
                attempt_count=1,
                policy_version=str(artifact.get("policy_version") or ""),
            )
            await saga.schedule_purge(session)
        else:
            await session.execute(
                update(Document).where(Document.doc_id == doc_id).values(**registry_updates)
            )
        await session.commit()

    summary.rows_total = len(parsed_records)
    summary.status = registry_updates["ingest_status"]
    return summary


async def _prepare_reingest_if_needed(
    doc_id: uuid.UUID,
    config: dict[str, Any],
    qdrant_router: Any,
    session: Any,
    document_context: dict[str, Any],
) -> None:
    """Deprecated test helper — production uses generation swap."""
    from spark.core.logging import get_logger
    from spark.db.models.docs import Document, DocumentChunk
    from spark.ingestion.index.qdrant_writer import QdrantRouter

    log = get_logger(__name__)
    if not _expects_qdrant_output(config):
        return
    prior_chunks = await session.scalar(
        select(func.count()).select_from(DocumentChunk).where(DocumentChunk.doc_id == doc_id)
    )
    if not prior_chunks:
        doc = await session.get(Document, doc_id)
        if not doc or doc.chunks_count == 0:
            return
    coll = _qdrant_collection(config, document_context)
    if isinstance(qdrant_router, QdrantRouter):
        await qdrant_router.clear_for_reingest(doc_id, session, collection=coll)
    log.info("reingest_prepared", doc_id=str(doc_id), prior_chunks=prior_chunks or 0)


def run_pipeline_sync(*args: Any, **kwargs: Any) -> JobSummary:
    async def _run() -> JobSummary:
        try:
            return await run_pipeline(*args, **kwargs)
        finally:
            from spark.core.cache import Cache
            from spark.core.database import engine

            await engine.dispose()
            # Reset the async Redis client so the next Celery task (which runs
            # in a fresh asyncio.run() event loop) gets a new connection.
            # redis.asyncio binds asyncio Lock/Future objects to the loop it was
            # created in; reusing the same client across loops causes
            # "Future attached to a different loop" errors on task 2+.
            await Cache.get().close_for_worker()

    return asyncio.run(_run())
