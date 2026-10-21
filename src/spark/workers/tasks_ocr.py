"""Celery tasks for heavy OCR work (isolated ocr_heavy queue)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from spark.core.logging import get_logger
from spark.ingestion.parsers.image_ocr_parser import _ocr_pdf_page_numbers
from spark.workers.celery_app import celery_app

log = get_logger(__name__)


@celery_app.task(
    name="spark.workers.tasks_ocr.ocr_pdf_pages_task",
    bind=True,
    acks_late=True,
)
def ocr_pdf_pages_task(
    self: Any,
    pdf_path: str,
    page_numbers: list[int],
    *,
    lang: str = "tha+eng",
    dpi: int = 200,
    preprocess: dict[str, Any] | None = None,
    cleanup: bool = False,
) -> dict[str, Any]:
    """OCR selected PDF pages on the ocr_heavy worker pool (idempotent per path+pages).

    Args:
        cleanup: When True the task deletes *pdf_path* after processing.
                 Set by the ingest pipeline when it copies the file to a
                 stable temp path so the OCR task owns its lifecycle.
    """
    path = Path(pdf_path)

    # Guard: the ingest task may have already cleaned up the source file
    # (e.g. after a timeout/restart). Return an empty result so stale
    # queued tasks fail gracefully instead of raising an unhandled exception.
    if not path.exists():
        log.warning(
            "ocr_heavy_file_missing",
            task_id=self.request.id,
            file=str(path),
            detail="source PDF was deleted before OCR worker started; returning empty result",
        )
        return {"pages": [], "error": "file_not_found"}

    log.info(
        "ocr_heavy_task_start",
        task_id=self.request.id,
        file=str(path),
        pages=len(page_numbers),
    )
    try:
        pages = _ocr_pdf_page_numbers(
            path,
            page_numbers,
            lang=lang,
            dpi=dpi,
            preprocess=preprocess,
        )
        return {
            "pages": [
                {
                    "page_number": page_num,
                    "text": page.text,
                    "confidence": page.confidence,
                }
                for page_num, page in sorted(pages.items())
            ]
        }
    finally:
        if cleanup:
            try:
                path.unlink(missing_ok=True)
                log.debug("ocr_heavy_temp_cleaned", file=str(path))
            except OSError as exc:
                log.warning("ocr_heavy_temp_cleanup_failed", file=str(path), error=str(exc))
