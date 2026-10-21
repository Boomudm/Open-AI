from __future__ import annotations

import asyncio
import re
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from spark.core.config import settings
from spark.core.logging import get_logger
from spark.ingestion.chunk.registry import PARSER_VERSION, chunk_blocks, leaf_metadata_fields
from spark.ingestion.chunk.strategies import is_parent_child_strategy
from spark.ingestion.config_resolver import ResolvedIngestConfig, get_chunking_config
from spark.ingestion.ocr_quality import OCRQualityTracker, chunk_index_rejected
from spark.ingestion.parse.blocks import ParsedBlock
from spark.ingestion.parse.layout import get_layout_parser
from spark.ingestion.parse.layout.fallback_pypdf import extract_pages_raw
from spark.ingestion.parse.layout.types import LayoutBlock, LayoutPage
from spark.ingestion.parse.table_object import TableObject
from spark.ingestion.parse.warnings import OCRQualityWarning, ParseWarningCollector, TableExtractWarning
from spark.ingestion.parsers.image_ocr_parser import (
    OCRPage,
    OCRUnavailableError,
    _ocr_pdf_extract_pages,
    _ocr_pdf_page_numbers,
)
from spark.ingestion.parsers.vision_diagram import (
    DEFAULT_TIMEOUT_SECONDS as DEFAULT_VISION_TIMEOUT_SECONDS,
)
from spark.ingestion.parsers.vision_diagram import (
    DEFAULT_VISION_PROFILE,
    extract_diagram_page,
    rasterize_pdf_page,
)
from spark.ingestion.parsers.vision_diagram import (
    VisionExtractionUnavailableError as _VisionUnavailable,
)
from spark.ingestion.parsers.base import ParsedRecord, ParserError, ParserPlugin

log = get_logger(__name__)

DEFAULT_MIN_CHARS_PER_PAGE = 20
_DRAWING_NO_RE = re.compile(r"\bEE[- ]?(\d+)\b", re.IGNORECASE)


def _extract_pages(pdf_path: Path) -> tuple[int, list[tuple[int, str, str]]]:
    """Backward-compatible page extraction for tests and OCR pipeline."""
    return extract_pages_raw(pdf_path)


def _page_needs_ocr(text: str, min_chars: int) -> bool:
    stripped = (text or "").strip()
    if len(stripped) < min_chars:
        return True
    if len(stripped) < 100 and not any(c.isalpha() for c in stripped):
        return True
    return False


def _run_ocr_pages(
    pdf_path: Path,
    ocr_targets: list[int],
    ocr_cfg: dict[str, Any],
) -> dict[int, OCRPage]:
    lang = ocr_cfg.get("lang", "tha+eng")
    dpi = int(ocr_cfg.get("dpi", 200) or 200)
    preprocess = ocr_cfg.get("preprocess") or None
    return _ocr_pdf_page_numbers(
        pdf_path,
        ocr_targets,
        lang=lang,
        dpi=dpi,
        preprocess=preprocess,
    )


def _ocr_worker_available(probe_timeout: float) -> bool:
    """Bounded check for a reachable broker + live ``ocr_heavy`` worker.

    Returns False fast (never the 20-retry Redis loop) when the broker is down or
    no worker is consuming, so callers can fall back to inline OCR. Any error is
    treated as "unavailable".
    """
    try:
        from spark.workers.celery_app import celery_app

        # Fail fast on a down broker — no connection retry storm.
        conn = celery_app.connection()
        try:
            conn.ensure_connection(max_retries=0, timeout=probe_timeout)
        finally:
            conn.release()

        replies = celery_app.control.ping(timeout=probe_timeout)
        return bool(replies)
    except Exception as exc:  # noqa: BLE001 — any failure means "not available"
        log.warning("ocr_worker_probe_failed", error=str(exc))
        return False


async def _await_celery_result(async_result: Any, timeout_sec: int) -> dict[str, Any]:
    import time

    deadline = time.monotonic() + timeout_sec
    while not async_result.ready():
        if time.monotonic() >= deadline:
            raise ParserError("ocr_timeout", f"OCR worker timed out after {timeout_sec}s")
        await asyncio.sleep(0.5)
    # disable_sync_subtasks=False suppresses Celery's "Never call result.get()
    # within a task" warning.  We poll ready() above so this is not a deadlock
    # risk; the OCR task runs on a separate ocr_heavy queue / worker process.
    return async_result.get(propagate=True, disable_sync_subtasks=False)


async def _run_ocr_pages_async(
    pdf_path: Path,
    ocr_targets: list[int],
    ocr_cfg: dict[str, Any],
) -> dict[int, OCRPage]:
    import shutil
    import uuid as _uuid

    from spark.storage.temp import ingest_temp_dir
    from spark.workers.tasks_ocr import ocr_pdf_pages_task

    lang = ocr_cfg.get("lang", "tha+eng")
    dpi = int(ocr_cfg.get("dpi", 200) or 200)
    preprocess = ocr_cfg.get("preprocess") or None
    timeout_sec = int(ocr_cfg.get("async_timeout", 600) or 600)

    # Copy the PDF to a stable path owned by the OCR task so that the file
    # persists even if the ingest task's context manager cleans up the
    # materialized temp file before the OCR worker finishes (e.g. on timeout
    # or Celery worker restart).  The OCR task deletes the copy on completion.
    ocr_copy = ingest_temp_dir() / f"ocr_{_uuid.uuid4()}{pdf_path.suffix or '.pdf'}"
    try:
        await asyncio.get_running_loop().run_in_executor(
            None, shutil.copy2, str(pdf_path), str(ocr_copy)
        )
    except Exception as exc:
        log.warning("ocr_copy_failed_using_original", file=str(pdf_path), error=str(exc))
        ocr_copy = pdf_path  # fall back to original; lifecycle risk remains

    log.info(
        "ocr_async_enqueue",
        file=str(ocr_copy),
        pages=len(ocr_targets),
        queue="ocr_heavy",
    )
    async_result = ocr_pdf_pages_task.apply_async(
        args=[str(ocr_copy), ocr_targets],
        kwargs={"lang": lang, "dpi": dpi, "preprocess": preprocess, "cleanup": ocr_copy != pdf_path},
        queue="ocr_heavy",
    )
    payload = await _await_celery_result(async_result, timeout_sec)
    out: dict[int, OCRPage] = {}
    for item in payload.get("pages") or []:
        page_num = int(item["page_number"])
        out[page_num] = OCRPage(
            page_number=page_num,
            text=item.get("text") or "",
            confidence=item.get("confidence"),
        )
    return out


async def _apply_per_page_ocr_async(
    pdf_path: Path,
    pages: list[tuple[int, str, str]],
    ocr_cfg: dict[str, Any],
) -> tuple[list[tuple[int, str, str, float | None]], dict[str, Any]]:
    min_chars = int(ocr_cfg.get("min_chars_per_page", DEFAULT_MIN_CHARS_PER_PAGE) or DEFAULT_MIN_CHARS_PER_PAGE)
    if ocr_cfg.get("force_all_pages"):
        ocr_targets = [page_num for page_num, _, _ in pages]
    else:
        ocr_targets = [
            page_num
            for page_num, page_text, _source in pages
            if _page_needs_ocr(page_text, min_chars)
        ]
    if not ocr_targets:
        return [(p, t, s, None) for p, t, s in pages], {}

    async_threshold = int(ocr_cfg.get("async_page_threshold", 2) or 2)
    use_async = bool(ocr_cfg.get("async", True)) and len(ocr_targets) >= async_threshold
    if settings.spark_profile == "test" or settings.spark_testing:
        use_async = False

    loop = asyncio.get_running_loop()

    def _run_inline() -> dict[int, OCRPage]:
        return _run_ocr_pages(pdf_path, ocr_targets, ocr_cfg)

    # Pre-flight: if inline fallback is enabled, only commit to the async path when
    # an ocr_heavy worker is actually reachable. This avoids blocking up to
    # `async_timeout` (default 600s) when the broker is down or no worker consumes.
    if use_async and settings.ingest_ocr_inline_fallback:
        probe_timeout = float(
            ocr_cfg.get("async_probe_timeout", settings.ingest_ocr_worker_probe_timeout)
            or settings.ingest_ocr_worker_probe_timeout
        )
        worker_up = await loop.run_in_executor(None, _ocr_worker_available, probe_timeout)
        if not worker_up:
            log.warning(
                "ocr_async_worker_unavailable_inline_fallback",
                file=str(pdf_path),
                pages=len(ocr_targets),
            )
            use_async = False

    if use_async:
        try:
            ocr_pages = await _run_ocr_pages_async(pdf_path, ocr_targets, ocr_cfg)
        except Exception as exc:  # noqa: BLE001
            if not settings.ingest_ocr_inline_fallback:
                raise
            log.warning(
                "ocr_async_failed_inline_fallback",
                file=str(pdf_path),
                pages=len(ocr_targets),
                error=str(exc),
            )
            use_async = False
            ocr_pages = await loop.run_in_executor(None, _run_inline)
    else:
        ocr_pages = await loop.run_in_executor(None, _run_inline)

    updated: list[tuple[int, str, str, float | None]] = []
    ocr_page_count = 0
    ocr_char_count = 0
    ocr_confidence_min: float | None = None

    for page_num, page_text, source in pages:
        confidence: float | None = None
        if page_num in ocr_pages:
            ocr_page = ocr_pages[page_num]
            if ocr_page.text.strip():
                page_text = ocr_page.text
                source = "ocr"
                confidence = ocr_page.confidence
                ocr_page_count += 1
                ocr_char_count += len(ocr_page.text.strip())
                if confidence is not None:
                    ocr_confidence_min = (
                        confidence
                        if ocr_confidence_min is None
                        else min(ocr_confidence_min, confidence)
                    )
        updated.append((page_num, page_text, source, confidence))

    stats = {
        "ocr_page_count": ocr_page_count,
        "ocr_char_count": ocr_char_count,
        "ocr_confidence_min": ocr_confidence_min,
        "ocr_target_pages": len(ocr_targets),
        "ocr_async": use_async,
    }
    return updated, stats


def _extract_drawing_no(page_text: str) -> str | None:
    match = _DRAWING_NO_RE.search(page_text or "")
    if not match:
        return None
    return f"EE-{match.group(1)}"


async def _apply_vision_extraction(
    pdf_path: Path,
    pages: list[tuple[int, str, str]],
    vision_cfg: dict[str, Any],
) -> tuple[list[tuple[int, str, str]], set[int], dict[int, Any]]:
    """Replace vector-drawing pages' text with a vision-LLM-derived analysis.

    Returns the updated ``pages`` list (only flagged pages' text/source
    change), the set of page numbers where extraction did not produce a
    parsed structured result (still indexed — never dropped — but flagged
    ``needs_review`` by the caller so a human knows to check the source page),
    and the per-page ``DiagramExtraction`` objects so the caller can build
    document-level index/synthesis chunks from them.
    """
    from spark.ingestion.parse.pdf_vector_density import (
        DEFAULT_CURVE_DENSITY_TRIGGER,
        DEFAULT_MAX_TEXT_CHARS,
        vector_drawing_pages,
    )

    loop = asyncio.get_running_loop()
    curve_trigger = int(vision_cfg.get("curve_density_trigger", DEFAULT_CURVE_DENSITY_TRIGGER))
    max_text_chars = int(vision_cfg.get("max_text_chars", DEFAULT_MAX_TEXT_CHARS))
    flagged = await loop.run_in_executor(
        None,
        lambda: vector_drawing_pages(
            pdf_path, curve_density_trigger=curve_trigger, max_text_chars=max_text_chars
        ),
    )
    if not flagged:
        return pages, set(), {}

    llm_profile = str(vision_cfg.get("llm_profile", DEFAULT_VISION_PROFILE))
    fallback_profiles = tuple(str(p) for p in (vision_cfg.get("llm_profile_fallbacks") or ()))
    dpi = int(vision_cfg.get("dpi", 200))
    timeout_seconds = float(vision_cfg.get("timeout_seconds", DEFAULT_VISION_TIMEOUT_SECONDS))
    original_text = {p: t for p, t, _s in pages}
    max_concurrency = int(
        vision_cfg.get("max_concurrency", settings.ingest_vision_max_concurrency)
        or settings.ingest_vision_max_concurrency
    )
    semaphore = asyncio.Semaphore(max(1, max_concurrency))

    async def _process(page_num: int) -> tuple[int, str, Any]:
        async with semaphore:
            drawing_no = _extract_drawing_no(original_text.get(page_num, ""))
            try:
                image = await loop.run_in_executor(
                    None, lambda: rasterize_pdf_page(pdf_path, page_num, dpi=dpi)
                )
            except _VisionUnavailable as exc:
                log.warning("vision_rasterize_failed", file=str(pdf_path), page=page_num, error=str(exc)[:200])
                from spark.ingestion.parsers.vision_diagram import DiagramExtraction

                extraction = DiagramExtraction(analysis="", parsed_ok=False)
            else:
                extraction = await extract_diagram_page(
                    image,
                    llm_profile=llm_profile,
                    fallback_profiles=fallback_profiles,
                    timeout_seconds=timeout_seconds,
                )
        text = extraction.to_page_content(page_number=page_num, drawing_no=drawing_no)
        raw_text = original_text.get(page_num, "").strip()
        if raw_text:
            # Title-block text (project/customer/revision) is real, already-extracted
            # text on these pages — the vision analysis above replaces it as the
            # page's primary content, so keep it from being silently dropped.
            text = f"{text}\n\n### ข้อความในแบบ (Title Block)\n{raw_text}"
        return page_num, text, extraction

    results = await asyncio.gather(*(_process(p) for p in sorted(flagged)))
    vision_text = {page_num: text for page_num, text, _e in results}
    needs_review = {page_num for page_num, _text, e in results if not e.parsed_ok}
    extractions = {page_num: e for page_num, _text, e in results}

    # A single failed page degrades gracefully (that page is indexed with a
    # needs-review flag). Every page failing is not degradation — it means the
    # vision backend is down, out of quota, or misconfigured, and the "drawing"
    # is about to be indexed as nothing but title blocks. Committing that would
    # swap a useless generation over the good one already being served (observed:
    # the KKU daily limit hit mid-run and replaced a whole 14-sheet binder with
    # empty pages, while the job still reported "completed"). Fail instead — the
    # error is retryable, and active_ingest_generation only flips on success, so
    # the previous generation keeps serving.
    if flagged and not any(e.analysis for _p, _t, e in results):
        raise ParserError(
            "vision_backend_unavailable",
            f"vision extraction returned nothing for all {len(flagged)} diagram pages "
            f"(profile {llm_profile}) — refusing to index the drawing as empty; "
            "check the model backend/quota and retry",
        )
    updated_pages = [
        (p, vision_text[p], "vision") if p in vision_text else (p, t, s) for p, t, s in pages
    ]
    log.info(
        "vision_diagram_extraction_complete",
        file=str(pdf_path),
        pages_flagged=len(flagged),
        pages_needing_review=len(needs_review),
    )
    return updated_pages, needs_review, extractions


def _pages_to_layout_pages(pages: list[tuple[int, str, str]]) -> list[LayoutPage]:
    layout_pages: list[LayoutPage] = []
    for page_num, page_text, source in pages:
        blocks = []
        if page_text.strip():
            blocks.append(
                LayoutBlock(
                    block_id=f"page-{page_num}",
                    page_number=page_num,
                    block_type="text",
                    text=page_text,
                    extraction_source=source,
                )
            )
        layout_pages.append(
            LayoutPage(
                page_number=page_num,
                blocks=blocks,
                extraction_source=source,
            )
        )
    return layout_pages


def _layout_pages_to_blocks(
    layout_pages: list[LayoutPage],
    page_sources: dict[int, str],
) -> list[ParsedBlock]:
    blocks: list[ParsedBlock] = []
    for layout_page in layout_pages:
        page_num = layout_page.page_number
        source = page_sources.get(page_num, layout_page.extraction_source)
        if not layout_page.blocks:
            continue
        for order, layout_block in enumerate(layout_page.blocks):
            if not layout_block.text.strip():
                continue
            blocks.append(
                ParsedBlock(
                    block_type="paragraph",
                    text=layout_block.text,
                    page=page_num,
                    reading_order=order,
                    section_path=list(layout_block.section_path),
                    metadata={
                        "extraction_source": source,
                        "parser_version": PARSER_VERSION,
                        "layout_parser": layout_block.extraction_source,
                    },
                )
            )
    return blocks


def _extract_table_objects(pdf_path: Path, page_count: int) -> list[TableObject]:
    from spark.ingestion.parse.table_object import extract_all_tables_batch

    return extract_all_tables_batch(pdf_path)


class PDFParser(ParserPlugin):
    name = "pdf"
    supported_extensions = (".pdf",)

    async def parse(self, file_path: Path, config: dict[str, Any]) -> AsyncIterator[ParsedRecord]:
        loop = asyncio.get_running_loop()
        document_type = (
            config.document_type
            if isinstance(config, ResolvedIngestConfig)
            else str(config.get("document_type") or "")
        )
        layout_parser_name = None
        if isinstance(config, ResolvedIngestConfig):
            layout_parser_name = getattr(config, "layout_parser", None)
        else:
            layout_parser_name = (config.get("layout") or {}).get("parser")

        try:
            layout_parser = get_layout_parser(layout_parser_name)
            page_count, layout_pages, _layout_tables = await loop.run_in_executor(
                None,
                layout_parser.parse,
                file_path,
            )
            pages = [
                (
                    lp.page_number,
                    lp.blocks[0].text if lp.blocks else "",
                    lp.extraction_source,
                )
                for lp in layout_pages
            ]
        except Exception as exc:
            raise ParserError("parser_failed", f"cannot read PDF: {exc}") from exc

        vision_cfg = config.get("vision") or {}
        vision_needs_review: set[int] = set()
        vision_pages: set[int] = set()
        vision_extractions: dict[int, Any] = {}
        if vision_cfg.get("enabled"):
            pages, vision_needs_review, vision_extractions = await _apply_vision_extraction(
                file_path, pages, vision_cfg
            )
            layout_pages = _pages_to_layout_pages(pages)
            vision_pages = {p for p, _t, s in pages if s == "vision"}

        ocr_cfg = config.get("ocr") or {}
        ocr_stats: dict[str, Any] = {}
        sparse_ocr_stats: dict[str, Any] = {}
        ocr_tracker = OCRQualityTracker()
        page_confidence: dict[int, float | None] = {}

        min_chars_per_page = int(ocr_cfg.get("min_chars_per_page", 50) or 50)
        _avg_chars = sum(len(t.strip()) for _, t, _ in pages) / max(len(pages), 1)
        has_extractable_page = any(len(t.strip()) >= min_chars_per_page for _, t, _ in pages)
        if _avg_chars < 50 and not has_extractable_page:
            lang = ocr_cfg.get("lang", "tha+eng")
            dpi = int(ocr_cfg.get("dpi", 200) or 200)
            try:
                ocr_result = await loop.run_in_executor(
                    None, lambda: _ocr_pdf_extract_pages(file_path, lang=lang, dpi=dpi)
                )
            except OCRUnavailableError as exc:
                log.error("ocr_unavailable", file=str(file_path), error=str(exc))
                raise ParserError("ocr_unavailable", str(exc)) from exc

            pages_with_conf: list[tuple[int, str, str, float | None]] = []
            for page in ocr_result.pages:
                page_num = page.page_number or len(pages_with_conf) + 1
                pages_with_conf.append((page_num, page.text, "ocr", page.confidence))
                ocr_tracker.add(page_num, "ocr", page.confidence)
                page_confidence[page_num] = page.confidence
            pages = [(p, t, s) for p, t, s, _ in pages_with_conf]
            layout_pages = _pages_to_layout_pages(pages)
            page_count = page_count or ocr_result.page_count
            ocr_stats = {
                "ocr_page_count": ocr_result.page_count,
                "ocr_char_count": ocr_result.char_count,
                "ocr_confidence_min": ocr_result.min_confidence,
            }
        else:
            try:
                pages_with_conf, sparse_ocr_stats = await _apply_per_page_ocr_async(
                    file_path,
                    pages,
                    ocr_cfg,
                )
            except OCRUnavailableError as exc:
                if any(page_text.strip() for _, page_text, _ in pages):
                    log.warning(
                        "per_page_ocr_unavailable",
                        file=str(file_path),
                        error=str(exc)[:200],
                    )
                    pages_with_conf = [(p, t, s, None) for p, t, s in pages]
                    sparse_ocr_stats = {}
                else:
                    log.error("ocr_unavailable", file=str(file_path), error=str(exc))
                    raise ParserError("ocr_unavailable", str(exc)) from exc
            pages = [(p, t, s) for p, t, s, _ in pages_with_conf]
            layout_pages = _pages_to_layout_pages(pages)
            for page_num, _page_text, source, confidence in pages_with_conf:
                ocr_tracker.add(page_num, source, confidence)
                page_confidence[page_num] = confidence
            if sparse_ocr_stats.get("ocr_page_count"):
                ocr_stats = sparse_ocr_stats

        try:
            table_objects = await loop.run_in_executor(
                None,
                lambda: _extract_table_objects(file_path, page_count),
            )
            if vision_pages:
                # Vector-drawing pages are line art — pdfplumber "tables" there
                # are the drawing's border/coordinate grid, not data (observed:
                # 80 phantom tables like "| F | E | D | C | B |" from one
                # 14-sheet wiring binder, none flagged needs_review). The
                # vision narrative is the indexed representation of those pages.
                before = len(table_objects)
                table_objects = [t for t in table_objects if t.page not in vision_pages]
                if before != len(table_objects):
                    log.info(
                        "pdf_tables_dropped_vision_pages",
                        file=str(file_path),
                        dropped=before - len(table_objects),
                        kept=len(table_objects),
                    )
        except Exception as exc:
            log.warning("pdf_table_extract_failed", file=str(file_path), error=str(exc)[:200])
            table_objects = []
            warning_sink = config.get("_parse_warnings")
            if isinstance(warning_sink, ParseWarningCollector):
                warning_sink.add(
                    TableExtractWarning(
                        file=str(file_path),
                        error=str(exc),
                        page_count=page_count,
                    )
                )

        ocr_quality_detail = ocr_tracker.enforce_job_quality(
            document_type=document_type, total_page_count=page_count
        )
        if ocr_quality_detail:
            log.warning("ocr_quality_low", file=str(file_path), detail=ocr_quality_detail)
            warning_sink = config.get("_parse_warnings")
            if isinstance(warning_sink, ParseWarningCollector):
                warning_sink.add(
                    OCRQualityWarning(
                        file=str(file_path),
                        detail=ocr_quality_detail,
                        document_type=document_type,
                    )
                )

        chunking_cfg = get_chunking_config(config)
        chunk_size = int(chunking_cfg.get("chunk_size", 1200) or 1200)
        chunk_overlap = int(chunking_cfg.get("chunk_overlap", 200) or 200)
        strategy = chunking_cfg.get("strategy")
        mode = (chunking_cfg.get("mode") or "").lower()
        use_parent_child = mode == "parent_child" or is_parent_child_strategy(strategy)
        parent_chunk_size = int(chunking_cfg.get("parent_chunk_size", 2400) or 2400)
        parent_chunk_overlap = int(chunking_cfg.get("parent_chunk_overlap", 64) or 64)
        child_chunk_size = int(chunking_cfg.get("child_chunk_size", 512) or 512)
        child_chunk_overlap = int(chunking_cfg.get("child_chunk_overlap", 64) or 64)
        semantic_threshold = chunking_cfg.get("semantic_breakpoint_threshold")
        semantic_breakpoint_threshold = float(semantic_threshold) if semantic_threshold is not None else None

        log.info(
            "chunking_strategy_effective",
            file=str(file_path),
            strategy=strategy,
            mode=mode or None,
            parent_child=use_parent_child,
            layout_parser=layout_parser.name,
        )

        text_pages = [
            (page_num, page_text, extraction_source)
            for page_num, page_text, extraction_source in pages
            if page_text.strip()
        ]
        if not text_pages and not table_objects:
            raise ParserError(
                "no_extractable_text",
                "PDF has no extractable text; it may be scanned or image-only and needs OCR",
            )

        global_index = 0
        fallback_pages = sum(1 for _, _, src in text_pages if src.startswith("pdfplumber"))
        ocr_pages_used = sum(1 for _, _, src in text_pages if src == "ocr")
        table_pages = len({t.page for t in table_objects})
        rejected_chunks = 0

        if text_pages:
            page_sources = {page_num: src for page_num, _, src in text_pages}
            page_drawing_no = {
                page_num: drawing
                for page_num, page_text, _ in text_pages
                if (drawing := _extract_drawing_no(page_text))
            }
            doc_drawing_no = None
            if isinstance(config, dict):
                doc_drawing_no = (config.get("document_context") or {}).get("drawing_no")
            blocks = _layout_pages_to_blocks(layout_pages, page_sources)
            chunk_strategy = (
                "page_aware_parent_child" if use_parent_child else strategy
            )

            block_pairs = chunk_blocks(
                blocks,
                strategy=chunk_strategy,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                parent_chunk_size=parent_chunk_size,
                parent_chunk_overlap=parent_chunk_overlap,
                child_chunk_size=child_chunk_size,
                child_chunk_overlap=child_chunk_overlap,
                semantic_breakpoint_threshold=semantic_breakpoint_threshold,
                document_type=document_type,
                doc_id=config.get("_doc_id"),
            )

            for leaf, block_meta in block_pairs:
                if not leaf.text.strip():
                    continue
                page_num = block_meta.get("page")
                extraction_source = page_sources.get(page_num, "pypdf") if page_num else "pypdf"
                confidence = page_confidence.get(page_num) if page_num else None
                section_path = leaf.section_path or block_meta.get("section_path")
                if isinstance(section_path, list):
                    section_path = " > ".join(section_path)
                if chunk_index_rejected(confidence, extraction_source):
                    rejected_chunks += 1
                    yield ParsedRecord(
                        route="qdrant",
                        payload={
                            "page_content": leaf.text,
                            "page": page_num,
                            "chunk_index": global_index,
                            "page_count": page_count,
                            "extraction_source": extraction_source,
                            "ocr_rejected": True,
                            "needs_review": True,
                            "ocr_confidence": confidence,
                            "section_path": section_path,
                            "parser_version": PARSER_VERSION,
                            # Same required-field contract as the table branch below —
                            # this record is normally filtered out by validators.py's
                            # ocr_low_confidence check before reaching the writer, but
                            # satisfy the contract anyway in case that check is bypassed.
                            "chunk_level": "child",
                            "parent_chunk_id": "",
                            "parent_content": leaf.text,
                        },
                        text_for_embedding=leaf.text,
                        source_locator={"page": page_num, "chunk_index": global_index},
                    )
                    global_index += 1
                    continue

                payload: dict[str, Any] = {
                    "page_content": leaf.text,
                    "page": page_num,
                    "chunk_index": global_index,
                    "page_count": page_count,
                    "extraction_source": extraction_source,
                    "chunk_level": "child",
                    "parent_chunk_id": leaf.parent_chunk_id,
                    "parent_content": leaf.parent_text,
                    "parent_index": leaf.parent_index,
                    "child_index_in_parent": leaf.child_index,
                    "section_path": section_path,
                    "has_tables": False,
                    "parser_version": PARSER_VERSION,
                    **leaf_metadata_fields(leaf),
                }
                if ocr_stats.get("ocr_page_count") is not None:
                    payload["ocr_page_count"] = ocr_stats["ocr_page_count"]
                    payload["ocr_char_count"] = ocr_stats.get("ocr_char_count")
                if ocr_stats.get("ocr_confidence_min") is not None:
                    payload["ocr_confidence"] = ocr_stats["ocr_confidence_min"]
                if confidence is not None:
                    payload["page_ocr_confidence"] = confidence
                if page_num and page_num in page_drawing_no:
                    payload["drawing_no"] = page_drawing_no[page_num]
                elif doc_drawing_no:
                    payload["drawing_no"] = doc_drawing_no
                if extraction_source == "vision" and page_num in vision_needs_review:
                    # Vision model produced no parseable structure (unavailable,
                    # timed out, or a malformed response) — still indexed (never
                    # drop a diagram page) but flagged so a human knows to check
                    # the original page image before relying on this chunk.
                    payload["needs_review"] = True
                yield ParsedRecord(
                    route="qdrant",
                    payload=payload,
                    text_for_embedding=leaf.text,
                    source_locator={"page": page_num, "chunk_index": global_index},
                )
                global_index += 1

        for table in table_objects:
            confidence = page_confidence.get(table.page)
            extraction_source = "pypdf"
            for page_num, _, src in text_pages:
                if page_num == table.page:
                    extraction_source = src
                    break
            table_payload = {
                "page_content": table.markdown,
                "chunk_index": global_index,
                "page_count": page_count,
                "page": table.page,
                "extraction_source": extraction_source,
                "chunk_level": "table",
                # page_aware_parent_child requires parent_chunk_id/parent_content
                # on every record (see REQUIRED_PARSER_FIELDS_BY_CHUNKING_STRATEGY).
                # A table is never split into parent/child pieces — it's already
                # the atomic unit — so there's no real parent to reference. Leaving
                # these keys out entirely (as before) failed that contract check
                # and raised inside QdrantWriter.write(), taking the whole document
                # to DLQ after every other row had already been queued as "ok".
                # "" not None: ParsedRecord.__post_init__ round-trips the payload
                # through a Pydantic model with model_dump(exclude_none=True),
                # which silently drops a None value and re-introduces the missing
                # key — "" is the sentinel this codebase already uses elsewhere
                # (chunk/registry.py, chunk/sop_procedure.py) for "no parent".
                "parent_chunk_id": "",
                "parent_content": table.markdown,
                "section_path": f"Table {table.table_index}",
                "parser_version": PARSER_VERSION,
                **table.to_payload(),
            }
            if confidence is not None:
                table_payload["page_ocr_confidence"] = confidence
            yield ParsedRecord(
                route="qdrant",
                payload=table_payload,
                text_for_embedding=table.to_embed_text(),
                source_locator={"page": table.page, "chunk_index": global_index},
            )
            global_index += 1

        # Document-level chunks for multi-sheet drawings: a deterministic
        # device→pages index plus an LLM-synthesized whole-system overview.
        # These answer cross-page questions ("ถ้า M18 พังกระทบวงจรไหน", "ไล่สาย
        # ทั้งระบบ") that no single page's chunk can. page=0 marks
        # "whole document" — 0, not None, because ParsedRecord round-trips the
        # payload through model_dump(exclude_none=True) which would drop a None
        # and break the page_aware_parent_child required-field contract.
        synthesis_chunks: list[tuple[str, str]] = []
        parsed_analyses = {
            p: e.analysis
            for p, e in vision_extractions.items()
            if getattr(e, "parsed_ok", False) and getattr(e, "analysis", "")
        }
        if len(parsed_analyses) >= 2 and vision_cfg.get("document_synthesis", True):
            from spark.ingestion.parsers.vision_diagram import (
                build_device_page_index,
                split_doc_level_markdown,
                synthesize_document_overview,
            )

            index_md = build_device_page_index(parsed_analyses)
            if index_md:
                synthesis_chunks.append(("Device Index (ดัชนีอุปกรณ์)", index_md))
            overview_md = await synthesize_document_overview(
                parsed_analyses,
                llm_profile=str(vision_cfg.get("llm_profile", DEFAULT_VISION_PROFILE)),
                timeout_seconds=float(
                    vision_cfg.get("timeout_seconds", DEFAULT_VISION_TIMEOUT_SECONDS)
                ),
            )
            if overview_md:
                synthesis_chunks.append(
                    (
                        "System Overview (ภาพรวมระบบ)",
                        "## 🗺️ ภาพรวมระบบทั้งเอกสาร (System Overview)\n\n" + overview_md,
                    )
                )
            log.info(
                "vision_document_synthesis_complete",
                file=str(file_path),
                device_index=bool(index_md),
                overview=bool(overview_md),
            )
        for section_path, synthesis_text in synthesis_chunks:
            # These are atomic (parent_chunk_id="") so the chunker never splits
            # them — split here or a long index truncates at embed time.
            pieces = split_doc_level_markdown(synthesis_text)
            for part_no, piece in enumerate(pieces, start=1):
                piece_path = (
                    section_path
                    if len(pieces) == 1
                    else f"{section_path} — ตอนที่ {part_no}/{len(pieces)}"
                )
                yield ParsedRecord(
                    route="qdrant",
                    payload={
                        "page_content": piece,
                        "page": 0,
                        "chunk_index": global_index,
                        "page_count": page_count,
                        "extraction_source": "vision",
                        "chunk_level": "child",
                        "parent_chunk_id": "",
                        "parent_content": piece,
                        "section_path": piece_path,
                        "has_tables": False,
                        "parser_version": PARSER_VERSION,
                    },
                    text_for_embedding=piece,
                    source_locator={"page": 0, "chunk_index": global_index},
                )
                global_index += 1

        if global_index == 0:
            raise ParserError(
                "no_extractable_text",
                "PDF has no extractable text; it may be scanned or image-only and needs OCR",
            )

        log.info(
            "pdf_parse_complete",
            file=str(file_path),
            total_pages=page_count,
            pages=len(text_pages),
            chunks=global_index,
            rejected_ocr_chunks=rejected_chunks,
            fallback_pages=fallback_pages,
            table_pages=table_pages,
            table_objects=len(table_objects),
            ocr_pages=ocr_stats.get("ocr_page_count") or ocr_pages_used,
            ocr_target_pages=sparse_ocr_stats.get("ocr_target_pages", 0),
            parent_child=use_parent_child,
            block_pipeline=True,
            layout_parser=layout_parser.name,
        )
