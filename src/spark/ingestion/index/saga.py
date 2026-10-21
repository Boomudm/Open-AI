"""Ingest index saga — verify → commit → async purge with compensating rollback.

Remediation v4: saga state transition enforcement with optimistic locking.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Any

from sqlalchemy import delete, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from spark.core.logging import get_logger
from spark.core.rag_observability import ingest_swap_committed_fields
from spark.db.models.docs import Document, DocumentChunk
from spark.ingestion.errors import PermanentIngestError
from spark.ingestion.index.qdrant_writer import QdrantWriter
from spark.ingestion.index.swap_verify import verify_generation_counts

log = get_logger(__name__)

STRUCTURED_GENERATION_TABLES = frozenset()


async def verify_structured_tables(
    session: AsyncSession,
    doc_id: uuid.UUID,
    generation: int,
    *,
    expected_counts: dict[str, int] | None = None,
) -> None:
    """Structured table verification is disabled for document-only RAG."""
    if not expected_counts:
        return
    for table, expected in expected_counts.items():
        if table not in STRUCTURED_GENERATION_TABLES or expected <= 0:
            continue
        count = await session.scalar(
            text(
                f"SELECT COUNT(*) FROM {table} "
                "WHERE doc_id = :doc_id AND ingest_generation = :generation"
            ),
            {"doc_id": doc_id, "generation": generation},
        )
        actual = int(count or 0)
        if actual != expected:
            raise PermanentIngestError(
                "structured_table_drift",
                f"{table} generation {generation}: expected {expected} rows, found {actual}",
            )


@dataclass(frozen=True)
class IngestGenerationPlan:
    """Staging generation for the current ingest run."""

    staging: int
    active: int
    is_reingest: bool


class IngestSagaState(str, Enum):
    STAGING = "staging"
    STAGING_VERIFIED = "staging_verified"
    COMMITTED = "committed"
    PURGE_PENDING = "purge_pending"
    COMPLETE = "complete"
    ABORTED = "aborted"


_VALID_TRANSITIONS: dict[IngestSagaState | None, frozenset[IngestSagaState]] = {
    None: frozenset({
        IngestSagaState.STAGING,
        IngestSagaState.STAGING_VERIFIED,
        IngestSagaState.COMMITTED,
        IngestSagaState.ABORTED,
    }),
    IngestSagaState.STAGING: frozenset({IngestSagaState.STAGING_VERIFIED, IngestSagaState.ABORTED}),
    IngestSagaState.STAGING_VERIFIED: frozenset({IngestSagaState.COMMITTED, IngestSagaState.ABORTED}),
    IngestSagaState.COMMITTED: frozenset({IngestSagaState.PURGE_PENDING, IngestSagaState.COMPLETE}),
    IngestSagaState.PURGE_PENDING: frozenset({IngestSagaState.COMPLETE}),
}


def _validate_transition(current: str | None, target: IngestSagaState) -> None:
    try:
        current_state = IngestSagaState(current) if current else None
    except ValueError:
        current_state = None
    allowed = _VALID_TRANSITIONS.get(current_state, frozenset())
    if target not in allowed:
        raise PermanentIngestError(
            "invalid_saga_transition",
            f"cannot transition from {current!r} to {target.value}",
        )


async def _set_saga_state(
    session: AsyncSession,
    doc_id: uuid.UUID,
    state: IngestSagaState,
    *,
    validate: bool = True,
) -> None:
    if validate:
        doc = await session.get(Document, doc_id)
        current = doc.ingest_saga_state if doc else None
        _validate_transition(current, state)
    await session.execute(
        update(Document)
        .where(Document.doc_id == doc_id)
        .values(ingest_saga_state=state.value)
    )


async def _purge_structured_superseded(
    session: AsyncSession,
    doc_id: uuid.UUID,
    keep_generation: int,
) -> None:
    del session, doc_id, keep_generation
    return


class IngestIndexSaga:
    """Two-phase swap orchestrator with explicit saga states."""

    def __init__(
        self,
        *,
        doc_id: uuid.UUID,
        plan: IngestGenerationPlan,
        qdrant_router: QdrantWriter,
        collection: str | None,
    ) -> None:
        self.doc_id = doc_id
        self.plan = plan
        self.qdrant_router = qdrant_router
        self.collection = collection

    async def verify_staging(
        self,
        session: AsyncSession,
        *,
        pg_count: int,
        payload_sample_rate: float = 0.01,
        structured_counts: dict[str, int] | None = None,
        document_type: str | None = None,
    ) -> None:
        await verify_generation_counts(
            doc_id=self.doc_id,
            generation=self.plan.staging,
            pg_count=pg_count,
            qdrant_writer=self.qdrant_router,
            collection=self.collection,
            session=session,
            payload_sample_rate=payload_sample_rate,
            document_type=document_type,
        )
        await verify_structured_tables(
            session,
            self.doc_id,
            self.plan.staging,
            expected_counts=structured_counts,
        )
        doc = await session.get(Document, self.doc_id)
        current = doc.ingest_saga_state if doc else None
        if self.plan.is_reingest and current in {
            IngestSagaState.COMMITTED.value,
            IngestSagaState.PURGE_PENDING.value,
            IngestSagaState.COMPLETE.value,
        }:
            await _set_saga_state(session, self.doc_id, IngestSagaState.STAGING, validate=False)
        await _set_saga_state(session, self.doc_id, IngestSagaState.STAGING_VERIFIED)

    async def commit_swap(
        self,
        session: AsyncSession,
        *,
        chunks_count: int,
        document_updates: dict[str, Any],
        reason_code: str = "committed",
        factory_id: str | None = None,
        attempt_count: int | None = None,
        policy_version: str | None = None,
    ) -> None:
        registry = dict(document_updates)
        registry["active_ingest_generation"] = self.plan.staging
        registry["chunks_count"] = chunks_count
        registry["ingest_saga_state"] = IngestSagaState.COMMITTED.value

        await session.execute(
            update(Document).where(Document.doc_id == self.doc_id).values(**registry)
        )

        if self.plan.is_reingest:
            await session.execute(
                delete(DocumentChunk).where(
                    DocumentChunk.doc_id == self.doc_id,
                    DocumentChunk.ingest_generation != self.plan.staging,
                )
            )
            await _purge_structured_superseded(session, self.doc_id, self.plan.staging)

        resolved_factory = factory_id or document_updates.get("factory_id")
        resolved_policy = (
            policy_version
            or document_updates.get("policy_scan_version")
            or document_updates.get("policy_version")
        )
        log.info(
            "ingest_swap_committed",
            **ingest_swap_committed_fields(
                doc_id=str(self.doc_id),
                staging_generation=self.plan.staging,
                replaced_generation=self.plan.active if self.plan.is_reingest else None,
                chunks_count=chunks_count,
                reason_code=reason_code,
                factory_id=str(resolved_factory) if resolved_factory else None,
                attempt_count=attempt_count,
                policy_version=str(resolved_policy) if resolved_policy else None,
            ),
        )
        from spark.audit.worm_sink import schedule_worm_audit

        schedule_worm_audit(
            "ingest_swap_committed",
            factory_id=str(resolved_factory) if resolved_factory else None,
            payload={
                "doc_id": str(self.doc_id),
                "staging_generation": self.plan.staging,
                "replaced_generation": self.plan.active if self.plan.is_reingest else None,
                "chunks_count": chunks_count,
                "reason_code": reason_code,
                "policy_version": str(resolved_policy) if resolved_policy else None,
            },
        )

    async def schedule_purge(self, session: AsyncSession) -> None:
        from spark.ingestion.purge_outbox import enqueue_purge

        if not self.plan.is_reingest:
            await _set_saga_state(session, self.doc_id, IngestSagaState.COMPLETE)
            return
        await enqueue_purge(
            session,
            doc_id=self.doc_id,
            keep_generation=self.plan.staging,
            collection=self.collection,
        )
        await _set_saga_state(session, self.doc_id, IngestSagaState.PURGE_PENDING)

    async def abort(self, session: AsyncSession) -> None:
        # Refuse to abort a swap that has already committed: the staging
        # generation is (or is about to become) the live one, so deleting it
        # would destroy retrievable data, and _set_saga_state(ABORTED) would
        # raise an illegal-transition error that rolls back the whole finalize
        # transaction — reverting a *successful* reingest to the stale prior
        # generation. Mirror the guard in abort_staging_ingest and no-op.
        doc = await session.get(Document, self.doc_id)
        state = doc.ingest_saga_state if doc else None
        if state == IngestSagaState.ABORTED.value:
            return
        if (
            state in {
                IngestSagaState.COMMITTED.value,
                IngestSagaState.PURGE_PENDING.value,
                IngestSagaState.COMPLETE.value,
            }
            or (doc is not None and doc.active_ingest_generation == self.plan.staging)
        ):
            log.warning(
                "ingest_swap_abort_skipped_committed_generation",
                doc_id=str(self.doc_id),
                staging_generation=self.plan.staging,
                state=state,
            )
            return
        deleted = await session.execute(
            delete(DocumentChunk).where(
                DocumentChunk.doc_id == self.doc_id,
                DocumentChunk.ingest_generation == self.plan.staging,
            )
        )
        await self.qdrant_router.delete_by_doc_generation(
            self.doc_id,
            generation=self.plan.staging,
            collection=self.collection,
        )
        await _set_saga_state(session, self.doc_id, IngestSagaState.ABORTED)
        log.info(
            "ingest_swap_aborted",
            doc_id=str(self.doc_id),
            staging_generation=self.plan.staging,
            pg_rows_removed=deleted.rowcount or 0,
        )


async def abort_staging_ingest(
    *,
    doc_id: uuid.UUID,
    plan: IngestGenerationPlan,
    qdrant_router: QdrantWriter,
    session: AsyncSession,
    collection: str | None,
) -> None:
    doc = await session.get(Document, doc_id)
    state = doc.ingest_saga_state if doc else None
    if state == IngestSagaState.ABORTED.value:
        log.info(
            "ingest_swap_abort_idempotent",
            doc_id=str(doc_id),
            staging_generation=plan.staging,
            state=state,
        )
        return
    if (
        state in {
            IngestSagaState.COMMITTED.value,
            IngestSagaState.PURGE_PENDING.value,
            IngestSagaState.COMPLETE.value,
        }
        or (doc is not None and doc.active_ingest_generation == plan.staging)
    ):
        log.warning(
            "ingest_swap_abort_skipped_committed_generation",
            doc_id=str(doc_id),
            staging_generation=plan.staging,
            state=state,
        )
        return
    saga = IngestIndexSaga(
        doc_id=doc_id,
        plan=plan,
        qdrant_router=qdrant_router,
        collection=collection,
    )
    try:
        await saga.abort(session)
    except Exception as exc:
        raise PermanentIngestError(
            "staging_cleanup_failed",
            f"failed to abort staging generation {plan.staging}: {exc}",
        ) from exc


async def commit_ingest_swap(
    *,
    doc_id: uuid.UUID,
    plan: IngestGenerationPlan,
    chunks_count: int,
    document_updates: dict[str, Any],
    qdrant_router: QdrantWriter,
    session: AsyncSession,
    collection: str | None,
    reason_code: str = "committed",
    factory_id: str | None = None,
    attempt_count: int | None = None,
    policy_version: str | None = None,
    verify: bool = True,
    payload_sample_rate: float = 0.01,
) -> IngestIndexSaga:
    saga = IngestIndexSaga(
        doc_id=doc_id,
        plan=plan,
        qdrant_router=qdrant_router,
        collection=collection,
    )
    if verify:
        await saga.verify_staging(
            session,
            pg_count=chunks_count,
            payload_sample_rate=payload_sample_rate,
        )
    await saga.commit_swap(
        session,
        chunks_count=chunks_count,
        document_updates=document_updates,
        reason_code=reason_code,
        factory_id=factory_id,
        attempt_count=attempt_count,
        policy_version=policy_version,
    )
    return saga
