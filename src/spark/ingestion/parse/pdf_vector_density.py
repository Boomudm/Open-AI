"""Vector-primitive density signal — detects pages that are mostly line-art.

The existing OCR trigger (``pdf_parser.py::_page_needs_ocr``) only looks at
raw extracted character count. A CAD/EPLAN-exported wiring diagram typically
has a small, fixed title-block of real text (company name, drawing number,
revision) on every page, while the actual schematic content — wire runs,
terminal numbers, component symbols — is drawn as vector curves/lines with no
extractable text at all. That title-block text is enough to clear the
char-count threshold, so the page is accepted as "has enough text" even
though the real content was never captured. This module gives ingestion a
second signal — primitive density vs. text density — to catch that case.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from spark.core.logging import get_logger

log = get_logger(__name__)

DEFAULT_CURVE_DENSITY_TRIGGER = 200
# Absolute cap, not a ratio of primitive count: a title block is a roughly
# fixed handful of characters regardless of how graphically dense the rest of
# the page is (verified against a real 14-page wiring diagram: title-block
# char counts stayed in a narrow 369-463 band while primitive counts ranged
# 1503-13091). A ratio-based check made the trigger flaky page-to-page for
# exactly that reason — an absolute cap doesn't.
DEFAULT_MAX_TEXT_CHARS = 600


@dataclass(frozen=True)
class PagePrimitiveDensity:
    page_number: int
    curve_count: int
    line_count: int
    rect_count: int
    char_count: int

    @property
    def primitive_count(self) -> int:
        return self.curve_count + self.line_count + self.rect_count


def is_vector_drawing_page(
    density: PagePrimitiveDensity,
    *,
    curve_density_trigger: int = DEFAULT_CURVE_DENSITY_TRIGGER,
    max_text_chars: int = DEFAULT_MAX_TEXT_CHARS,
) -> bool:
    """True when a page is dense with vector graphics and has little real text.

    A page of normal paragraph text has ~0 curves/lines/rects. A page that's
    mostly a schematic has hundreds to thousands of small path segments
    (wires, symbols) and only a small, roughly fixed amount of real text (a
    title block, if any) regardless of how visually busy the drawing is.
    """
    if density.primitive_count < curve_density_trigger:
        return False
    return density.char_count < max_text_chars


def compute_pdf_page_densities(pdf_path: Path) -> dict[int, PagePrimitiveDensity]:
    """Open the PDF once via pdfplumber and compute a density signal per page.

    Best-effort: returns an empty mapping (never raises) if pdfplumber can't
    open the file — callers should treat that as "no vector-drawing pages
    detected" and fall through to the normal text/OCR pipeline.
    """
    try:
        import pdfplumber
    except ImportError:
        return {}

    densities: dict[int, PagePrimitiveDensity] = {}
    try:
        with pdfplumber.open(str(pdf_path)) as pdf:
            for page_index, page in enumerate(pdf.pages):
                try:
                    densities[page_index + 1] = PagePrimitiveDensity(
                        page_number=page_index + 1,
                        curve_count=len(page.curves or []),
                        line_count=len(page.lines or []),
                        rect_count=len(page.rects or []),
                        char_count=len(page.chars or []),
                    )
                except Exception as exc:  # noqa: BLE001 — best-effort per-page
                    log.debug(
                        "pdf_page_density_failed",
                        file=str(pdf_path),
                        page=page_index + 1,
                        error=str(exc)[:200],
                    )
    except Exception as exc:  # noqa: BLE001 — best-effort, never blocks ingestion
        log.warning("pdf_density_scan_failed", file=str(pdf_path), error=str(exc)[:200])
    return densities


def vector_drawing_pages(
    pdf_path: Path,
    *,
    curve_density_trigger: int = DEFAULT_CURVE_DENSITY_TRIGGER,
    max_text_chars: int = DEFAULT_MAX_TEXT_CHARS,
) -> set[int]:
    """1-based page numbers classified as vector line-art rather than text."""
    densities = compute_pdf_page_densities(pdf_path)
    return {
        page_num
        for page_num, density in densities.items()
        if is_vector_drawing_page(
            density,
            curve_density_trigger=curve_density_trigger,
            max_text_chars=max_text_chars,
        )
    }
