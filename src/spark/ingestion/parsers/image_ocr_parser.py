"""OCR parser backed by pytesseract.

The Python package is only a wrapper; the `tesseract` binary and language data
must also be present on the worker host.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from spark.core.logging import get_logger
from spark.ingestion.chunk.registry import chunk_text
from spark.ingestion.config_resolver import get_chunking_config
from spark.ingestion.ocr_quality import chunk_index_rejected
from spark.ingestion.parsers.base import ParsedRecord, ParserError, ParserPlugin

log = get_logger(__name__)


class OCRUnavailableError(RuntimeError):
    """Raised when OCR dependencies or runtime binaries are unavailable."""


@dataclass(frozen=True)
class OCRPage:
    page_number: int | None
    text: str
    confidence: float | None = None


@dataclass(frozen=True)
class OCRResult:
    pages: list[OCRPage]
    page_count: int
    char_count: int

    @property
    def text(self) -> str:
        return "\n\n".join(page.text for page in self.pages if page.text.strip())

    @property
    def min_confidence(self) -> float | None:
        confs = [p.confidence for p in self.pages if p.confidence is not None]
        return min(confs) if confs else None


def _ocr_error(message: str, exc: Exception | None = None) -> OCRUnavailableError:
    detail = message if exc is None else f"{message}: {exc}"
    return OCRUnavailableError(detail)


def _ocr_confidence(image: Any, lang: str) -> float | None:
    try:
        import pytesseract
    except ImportError:
        return None
    try:
        data = pytesseract.image_to_data(image, lang=lang, output_type=pytesseract.Output.DICT)
        confs = [int(c) for c in data.get("conf", []) if str(c).lstrip("-").isdigit() and int(c) >= 0]
        return round(sum(confs) / len(confs), 2) if confs else None
    except Exception:
        return None


def _pytesseract_image_to_string(image: Any, lang: str) -> tuple[str, float | None]:
    try:
        import pytesseract
    except ImportError as exc:
        raise _ocr_error("pytesseract is not installed", exc) from exc

    try:
        text = pytesseract.image_to_string(image, lang=lang) or ""
        confidence = _ocr_confidence(image, lang)
        return text, confidence
    except FileNotFoundError as exc:
        raise _ocr_error("tesseract binary is not installed or not on PATH", exc) from exc
    except Exception as exc:
        not_found = getattr(getattr(pytesseract, "pytesseract", None), "TesseractNotFoundError", None)
        tesseract_error = getattr(getattr(pytesseract, "pytesseract", None), "TesseractError", None)
        if not_found is not None and isinstance(exc, not_found):
            raise _ocr_error("tesseract binary is not installed or not on PATH", exc) from exc
        if tesseract_error is not None and isinstance(exc, tesseract_error):
            raise _ocr_error("tesseract OCR failed; verify language packs and input image", exc) from exc
        raise


def _result_from_pages(pages: list[OCRPage]) -> OCRResult:
    return OCRResult(
        pages=pages,
        page_count=len(pages),
        char_count=sum(len(page.text.strip()) for page in pages),
    )


def _preprocess_image(image: Any, preprocess: dict[str, Any] | None) -> Any:
    if not preprocess:
        return image
    try:
        from PIL import ImageEnhance
    except ImportError:
        return image
    contrast = float(preprocess.get("contrast", 1.0))
    if contrast != 1.0:
        image = ImageEnhance.Contrast(image.convert("RGB")).enhance(contrast)
    if preprocess.get("deskew"):
        try:
            import cv2
            import numpy as np

            arr = np.array(image.convert("RGB"))
            gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
            coords = np.column_stack(np.where(gray < 128))
            if len(coords) > 100:
                angle = cv2.minAreaRect(coords)[-1]
                if angle < -45:
                    angle = 90 + angle
                elif angle > 45:
                    angle = angle - 90
                if abs(angle) > 0.5:
                    image = image.rotate(-angle, expand=True, fillcolor="white")
        except ImportError:
            log.debug("opencv_not_installed_deskew_skipped")
    return image


def _ocr_image_file(
    path: Path, lang: str = "tha+eng", preprocess: dict[str, Any] | None = None
) -> OCRResult:
    try:
        from PIL import Image, ImageSequence
    except ImportError as exc:
        raise _ocr_error("pillow is not installed", exc) from exc

    try:
        with Image.open(path) as image:
            pages: list[OCRPage] = []
            for idx, frame in enumerate(ImageSequence.Iterator(image), start=1):
                processed = _preprocess_image(frame.convert("RGB"), preprocess)
                text, confidence = _pytesseract_image_to_string(processed, lang)
                pages.append(
                    OCRPage(
                        page_number=idx,
                        text=text,
                        confidence=confidence,
                    )
                )
            return _result_from_pages(pages)
    except OCRUnavailableError:
        raise
    except Exception as exc:
        raise RuntimeError(f"cannot OCR image: {exc}") from exc


def _ocr_pdf_extract_pages(
    path: Path,
    lang: str = "tha+eng",
    dpi: int = 200,
    preprocess: dict[str, Any] | None = None,
) -> OCRResult:
    try:
        from pdf2image import convert_from_path
    except ImportError as exc:
        raise _ocr_error("pdf2image is not installed", exc) from exc

    try:
        images = convert_from_path(str(path), dpi=dpi)
    except Exception as exc:
        raise _ocr_error("cannot render PDF for OCR; verify poppler is installed", exc) from exc

    pages = []
    for idx, image in enumerate(images, start=1):
        processed = _preprocess_image(image, preprocess)
        text, confidence = _pytesseract_image_to_string(processed, lang)
        pages.append(OCRPage(page_number=idx, text=text, confidence=confidence))
    return _result_from_pages(pages)


def _ocr_pdf_page_numbers(
    path: Path,
    page_numbers: list[int],
    *,
    lang: str = "tha+eng",
    dpi: int = 200,
    preprocess: dict[str, Any] | None = None,
) -> dict[int, OCRPage]:
    """OCR only the requested 1-based page numbers (per-page fallback for mixed PDFs)."""
    if not page_numbers:
        return {}
    try:
        from pdf2image import convert_from_path
    except ImportError as exc:
        raise _ocr_error("pdf2image is not installed", exc) from exc

    out: dict[int, OCRPage] = {}
    for page_num in sorted(set(page_numbers)):
        try:
            images = convert_from_path(
                str(path),
                dpi=dpi,
                first_page=page_num,
                last_page=page_num,
            )
        except Exception as exc:
            raise _ocr_error(
                "cannot render PDF page for OCR; verify poppler is installed",
                exc,
            ) from exc
        if not images:
            out[page_num] = OCRPage(page_number=page_num, text="", confidence=None)
            continue
        processed = _preprocess_image(images[0], preprocess)
        text, confidence = _pytesseract_image_to_string(processed, lang)
        out[page_num] = OCRPage(page_number=page_num, text=text, confidence=confidence)
    return out


def _ocr_extract(path: Path, lang: str = "tha+eng") -> str:
    return _ocr_image_file(path, lang=lang).text


class ImageOCRParser(ParserPlugin):
    name = "image_ocr"
    supported_extensions = (".png", ".jpg", ".jpeg", ".tiff", ".bmp")

    async def parse(self, file_path: Path, config: dict[str, Any]) -> AsyncIterator[ParsedRecord]:
        ocr_cfg = config.get("ocr") or {}
        lang = ocr_cfg.get("lang", "tha+eng")
        preprocess = ocr_cfg.get("preprocess") or {}
        try:
            result = await asyncio.get_running_loop().run_in_executor(
                None, lambda: _ocr_image_file(file_path, lang, preprocess or None)
            )
        except OCRUnavailableError as exc:
            log.error("ocr_unavailable", error=str(exc))
            raise ParserError("ocr_unavailable", str(exc)) from exc
        except RuntimeError as exc:
            log.error("ocr_failed", error=str(exc))
            raise ParserError("parser_failed", str(exc)) from exc

        text = result.text
        if not text.strip():
            raise ParserError("no_extractable_text", "OCR returned no text")

        chunking = get_chunking_config(config)
        strategy = chunking.get("strategy")
        global_index = 0
        for page in result.pages:
            page_text = page.text.strip()
            if not page_text:
                continue
            chunks = chunk_text(
                page_text,
                chunk_size=chunking.get("chunk_size", 800),
                chunk_overlap=chunking.get("chunk_overlap", 100),
                strategy=strategy,
            )
            for c in chunks:
                rejected = chunk_index_rejected(page.confidence, "ocr")
                payload: dict[str, Any] = {
                    "page_content": c,
                    "chunk_index": global_index,
                    "page": page.page_number,
                    "ocr_page_count": result.page_count,
                    "ocr_char_count": result.char_count,
                    "ocr_confidence": page.confidence,
                    "page_ocr_confidence": page.confidence,
                    "extraction_source": "ocr",
                }
                if rejected:
                    payload["ocr_rejected"] = True
                    payload["needs_review"] = True
                yield ParsedRecord(
                    route="qdrant",
                    payload=payload,
                    text_for_embedding=c,
                    source_locator={"chunk_index": global_index, "page": page.page_number},
                )
                global_index += 1
        if global_index == 0:
            raise ParserError("empty_after_chunking", "OCR text produced no chunks")
        log.info("image_ocr_parse_complete", file=str(file_path), chunks=global_index)
