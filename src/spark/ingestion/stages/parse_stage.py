"""Parse stage — config resolve + parser plugin (streaming batches)."""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession

from spark.ingestion.budget import ResourceBudgetTracker
from spark.ingestion.context import IngestContext, ParseStageResult
from spark.ingestion.document_type_resolver import detect_parser_for_path
from spark.ingestion.errors import PermanentIngestError
from spark.ingestion.parsers.base import ParsedRecord, ParserPlugin
from spark.ingestion.parse.warnings import ParseWarningCollector
from spark.services.ingest_events import append_ingestion_event


def resolve_parser_name(ctx: IngestContext) -> str:
    parser_name = str(ctx.document_context.get("parser") or ctx.config_raw.get("parser") or "")
    if parser_name == "auto":
        parser_name = detect_parser_for_path(ctx.file_path) or ""
    if not parser_name:
        raise PermanentIngestError(
            "unsupported_file_type",
            f"No parser is available for file extension {ctx.file_path.suffix or '<none>'}",
        )
    return parser_name


def _apply_parse_metadata(rec: ParsedRecord, ctx: IngestContext) -> None:
    if rec.payload.get("page_count") is not None:
        ctx.document_context["page_count"] = rec.payload["page_count"]
    for meta_key in ("ocr_page_count", "ocr_char_count", "ocr_confidence"):
        if rec.payload.get(meta_key) is not None:
            ctx.document_context[meta_key] = rec.payload[meta_key]
            if meta_key == "ocr_confidence":
                prev = ctx.document_context.get("ocr_confidence_min")
                val = float(rec.payload[meta_key])
                ctx.document_context["ocr_confidence_min"] = (
                    val if prev is None else min(float(prev), val)
                )


async def parse_batched(
    ctx: IngestContext,
    session: AsyncSession,
    parser: ParserPlugin,
    *,
    budget: ResourceBudgetTracker,
    batch_size: int = 64,
) -> AsyncIterator[tuple[list[ParsedRecord], int]]:
    """Yield micro-batches from the parser without retaining the full document."""
    config = dict(ctx.resolved_config.raw if ctx.resolved_config else ctx.config_raw)
    config["_doc_id"] = str(ctx.doc_id)
    warning_collector = ParseWarningCollector()
    config["_parse_warnings"] = warning_collector
    batch: list[ParsedRecord] = []
    rows_total = 0

    async for rec in parser.parse(ctx.file_path, config):
        rows_total += 1
        if rec.payload.get("page_count") is not None:
            budget.record_page_count(int(rec.payload["page_count"]))
        budget.record_chunk(rec)
        _apply_parse_metadata(rec, ctx)
        batch.append(rec)
        if len(batch) >= batch_size:
            yield batch, rows_total
            batch = []

    if batch:
        yield batch, rows_total

    ctx.parse_warnings.extend(warning_collector.warnings)
    for warning in warning_collector.warnings:
        await append_ingestion_event(
            session,
            job_id=ctx.job_id,
            stage="parse",
            code=str(warning.get("code") or "parse_warning"),
            level=str(warning.get("level") or "warning"),
            detail=warning,
        )

    await append_ingestion_event(
        session,
        job_id=ctx.job_id,
        stage="parse",
        code="parse_complete",
        detail={"rows_total": rows_total, "streaming": True},
    )


async def run_parse_stage(
    ctx: IngestContext,
    session: AsyncSession,
    parser: ParserPlugin,
) -> ParseStageResult:
    """Backward-compatible helper — counts rows only (no full record buffer)."""
    from spark.ingestion.budget import budget_from_config

    budget = ResourceBudgetTracker(budget_from_config(ctx.config_raw))
    rows_total = 0
    async for _batch, batch_rows_total in parse_batched(
        ctx,
        session,
        parser,
        budget=budget,
    ):
        rows_total = batch_rows_total
    return ParseStageResult(rows_total=rows_total)
