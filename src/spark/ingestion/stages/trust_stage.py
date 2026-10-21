"""Trust stage — per-record policy scan (no blob concatenation)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Literal

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from spark.db.models.docs import Document
from spark.db.models.ingestion import IngestionJob
from spark.ingestion.context import IngestContext, TrustScanState
from spark.ingestion.document_accumulator import DocumentAccumulator
from spark.ingestion.errors import PermanentIngestError
from spark.ingestion.job_reliability import content_policy_block_job_status
from spark.ingestion.parsers.base import ParsedRecord
from spark.core.metrics import ingest_quarantine_total
from spark.ingestion.stages.common import quarantine_registry_updates
from spark.ingestion.trust import TrustScanner, save_quarantine_artifact
from spark.ingestion.trust.models import PolicyResult
from spark.ingestion.trust.scanner import scan_batch
from spark.services.ingest_events import append_ingestion_event

TrustOutcomeKind = Literal["approve", "quarantine", "block"]


@dataclass
class TrustStageOutcome:
    kind: TrustOutcomeKind
    trust_state: TrustScanState
    summary_status: str | None = None


async def _apply_trust_result(
    ctx: IngestContext,
    session: AsyncSession,
    *,
    rows_total: int,
    batch: list[ParsedRecord],
    trust_result: PolicyResult,
    trust_state: TrustScanState,
    accumulator: DocumentAccumulator | None = None,
) -> TrustStageOutcome:
    trust_state.version = trust_result.policy_version
    trust_state.max_risk_score = max(trust_state.max_risk_score, trust_result.risk_score)
    trust_state.findings.extend(trust_result.findings_summary())

    await append_ingestion_event(
        session,
        job_id=ctx.job_id,
        stage="trust",
        code=f"trust_{trust_result.action}",
        detail={
            "policy_version": trust_result.policy_version,
            "finding_count": len(trust_result.findings),
            "risk_score": trust_result.risk_score,
            "batch_size": len(batch),
            "per_record_scan": True,
        },
    )

    if trust_result.action == "block":
        detail = (
            "; ".join(f.message for f in trust_result.findings[:3]) or "content policy block"
        )[:2000]
        now = datetime.now(tz=timezone.utc)
        block_status = content_policy_block_job_status()
        await session.execute(
            update(Document)
            .where(Document.doc_id == ctx.doc_id)
            .values(
                ingest_status="blocked",
                chunks_count=0,
                retrieval_enabled=False,
                policy_scan_version=trust_result.policy_version,
                content_risk_score=trust_result.risk_score,
                policy_findings_json=trust_result.findings_summary()[:50],
                quarantine_reason="content_policy_block",
            )
        )
        await session.execute(
            update(IngestionJob)
            .where(IngestionJob.job_id == ctx.job_id)
            .values(
                status=block_status,
                dlq_at=now if block_status == "dlq" else None,
                rows_total=rows_total,
                rows_ok=0,
                rows_skipped=rows_total,
                finished_at=now,
                last_error_code="content_policy_block",
                error_message=f"content_policy_block: {detail}"[:1000],
            )
        )
        await session.commit()
        raise PermanentIngestError("content_policy_block", detail)

    if trust_result.action == "quarantine":
        if accumulator is not None:
            accumulator.append_batch([], findings=trust_result.findings_summary())
        return TrustStageOutcome(
            kind="quarantine",
            trust_state=trust_state,
            summary_status="pending_release",
        )

    return TrustStageOutcome(kind="approve", trust_state=trust_state)


async def finalize_quarantine(
    ctx: IngestContext,
    session: AsyncSession,
    *,
    accumulator: DocumentAccumulator,
    rows_total: int,
    trust_state: TrustScanState,
    trust_outcome: TrustStageOutcome,
) -> TrustStageOutcome:
    """Persist full-document quarantine artifact after streaming drain completes."""
    if accumulator.record_count() != rows_total:
        raise PermanentIngestError(
            "quarantine_incomplete",
            f"artifact records={accumulator.record_count()} rows_total={rows_total}",
        )

    findings = list(trust_state.findings)
    if accumulator.trust_findings:
        findings = list({str(item): item for item in accumulator.trust_findings}.values())

    artifact_uri = await save_quarantine_artifact(
        ctx.doc_id,
        records=accumulator.all_records(),
        document_context=ctx.document_context,
        policy_version=trust_state.version or "unknown",
        findings=findings,
        risk_score=trust_state.max_risk_score,
        upload_sha256=ctx.file_hash_sha256,
    )
    registry_updates = quarantine_registry_updates(
        ctx.document_context,
        trust_result=SimpleNamespace(
            policy_version=trust_state.version or "unknown",
            risk_score=trust_state.max_risk_score,
            findings_summary=lambda: findings[:50],
        ),
        artifact_uri=artifact_uri,
    )
    now = datetime.now(tz=timezone.utc)
    await session.execute(
        update(Document).where(Document.doc_id == ctx.doc_id).values(**registry_updates)
    )
    await session.execute(
        update(IngestionJob)
        .where(IngestionJob.job_id == ctx.job_id)
        .values(
            status="pending_release",
            rows_total=rows_total,
            rows_ok=0,
            rows_skipped=rows_total,
            finished_at=now,
            last_error_code=None,
            error_message=None,
        )
    )
    await append_ingestion_event(
        session,
        job_id=ctx.job_id,
        stage="trust",
        code="quarantine_full_document",
        detail={
            "rows_total": rows_total,
            "artifact_records": accumulator.record_count(),
            "batches_processed": accumulator.batches_processed,
        },
    )
    ingest_quarantine_total.labels(str(ctx.document_type or "unknown")).inc()
    return trust_outcome


async def _scan_batch(
    ctx: IngestContext,
    session: AsyncSession,
    batch: list[ParsedRecord],
    *,
    rows_total: int,
    scanner: TrustScanner,
    trust_state: TrustScanState,
    accumulator: DocumentAccumulator | None = None,
) -> TrustStageOutcome:
    if not trust_state.enabled or not batch:
        return TrustStageOutcome(kind="approve", trust_state=trust_state)

    trust_result = await scan_batch(scanner, batch, ctx.document_context)
    return await _apply_trust_result(
        ctx,
        session,
        rows_total=rows_total,
        batch=batch,
        trust_result=trust_result,
        trust_state=trust_state,
        accumulator=accumulator,
    )


async def apply_post_chunk_policy(
    ctx: IngestContext,
    session: AsyncSession,
    records: list[ParsedRecord],
    *,
    rows_total: int,
    scanner: TrustScanner,
    trust_state: TrustScanState,
    accumulator: DocumentAccumulator | None = None,
) -> TrustStageOutcome | None:
    from spark.ingestion.trust.post_chunk_scan import scan_post_chunk_batch

    if not trust_state.enabled or not records:
        return None

    trust_result = await scan_post_chunk_batch(records, ctx, scanner)
    if trust_result is None:
        return None

    return await _apply_trust_result(
        ctx,
        session,
        rows_total=rows_total,
        batch=records,
        trust_result=trust_result,
        trust_state=trust_state,
        accumulator=accumulator,
    )


async def trust_batch(
    ctx: IngestContext,
    session: AsyncSession,
    batch: list[ParsedRecord],
    *,
    rows_total: int,
    scanner: TrustScanner,
    trust_state: TrustScanState,
    accumulator: DocumentAccumulator | None = None,
) -> TrustStageOutcome:
    return await _scan_batch(
        ctx,
        session,
        batch,
        rows_total=rows_total,
        scanner=scanner,
        trust_state=trust_state,
        accumulator=accumulator,
    )


async def apply_finalize_document_trust(
    ctx: IngestContext,
    session: AsyncSession,
    *,
    accumulator: DocumentAccumulator,
    rows_total: int,
    trust_state: TrustScanState,
    scanner: TrustScanner,
) -> TrustStageOutcome | None:
    """Full-document adversarial scan before swap — block/quarantine after staging index."""
    if not trust_state.enabled or accumulator.record_count() == 0:
        return None

    from spark.ingestion.trust.document_scan import scan_accumulator

    trust_result = await scan_accumulator(accumulator, ctx.document_context, scanner)
    trust_state.version = trust_result.policy_version
    trust_state.max_risk_score = max(trust_state.max_risk_score, trust_result.risk_score)
    trust_state.findings.extend(trust_result.findings_summary())

    await append_ingestion_event(
        session,
        job_id=ctx.job_id,
        stage="trust",
        code="trust_full_document_scan",
        detail={
            "finding_count": len(trust_result.findings),
            "risk_score": trust_result.risk_score,
            "action": trust_result.action,
            "records_scanned": accumulator.record_count(),
        },
    )

    if trust_result.action == "allow":
        return None

    outcome = await _apply_trust_result(
        ctx,
        session,
        rows_total=rows_total,
        batch=[],
        trust_result=trust_result,
        trust_state=trust_state,
        accumulator=accumulator,
    )
    return outcome


async def run_trust_stage(
    ctx: IngestContext,
    session: AsyncSession,
    parsed_records: list[ParsedRecord],
    *,
    scanner: TrustScanner,
    trust_state: TrustScanState,
    accumulator: DocumentAccumulator | None = None,
) -> TrustStageOutcome:
    return await trust_batch(
        ctx,
        session,
        parsed_records,
        rows_total=len(parsed_records),
        scanner=scanner,
        trust_state=trust_state,
        accumulator=accumulator,
    )
