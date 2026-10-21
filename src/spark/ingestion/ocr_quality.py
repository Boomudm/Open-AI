"""OCR confidence gates for ingest quality (Phase 4)."""

from __future__ import annotations

from dataclasses import dataclass, field

from spark.core.config import settings

# Keep in sync with spark.ingestion.trust.gate.SAFETY_DOCUMENT_TYPES (avoid circular import).
SAFETY_DOCUMENT_TYPES = frozenset({"sop", "machine_manual", "safety_certificate"})

# Safety manual types fail when >30% OCR blocks are below block threshold.
SAFETY_OCR_BLOCK_FAIL_RATIO = 0.30


class OCRQualityInsufficientError(Exception):
    """Raised when document-level OCR quality fails the block threshold."""

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.reason_code = "ocr_quality_insufficient"
        self.reason_detail = detail


@dataclass
class OCRPageStat:
    page_number: int
    extraction_source: str
    confidence: float | None = None


@dataclass
class OCRBlockStat:
    page_number: int
    extraction_source: str
    confidence: float | None
    block_index: int = 0


@dataclass
class OCRQualityTracker:
    pages: list[OCRPageStat] = field(default_factory=list)
    blocks: list[OCRBlockStat] = field(default_factory=list)

    def add(self, page_number: int, extraction_source: str, confidence: float | None) -> None:
        self.pages.append(
            OCRPageStat(
                page_number=page_number,
                extraction_source=extraction_source,
                confidence=confidence,
            )
        )
        if extraction_source == "ocr":
            self.add_block(page_number, extraction_source, confidence)

    def add_block(
        self,
        page_number: int,
        extraction_source: str,
        confidence: float | None,
        *,
        block_index: int = 0,
    ) -> None:
        self.blocks.append(
            OCRBlockStat(
                page_number=page_number,
                extraction_source=extraction_source,
                confidence=confidence,
                block_index=block_index,
            )
        )

    def confidence_for_page(self, page_number: int) -> float | None:
        for stat in self.pages:
            if stat.page_number == page_number:
                return stat.confidence
        return None

    def aggregate_min_confidence(self) -> float | None:
        confs = [p.confidence for p in self.pages if p.confidence is not None]
        return min(confs) if confs else None

    def ocr_page_count(self) -> int:
        return sum(1 for p in self.pages if p.extraction_source == "ocr")

    def ocr_block_count(self) -> int:
        return sum(1 for b in self.blocks if b.extraction_source == "ocr")

    def low_index_pages(self) -> list[int]:
        threshold = settings.ocr_index_min_confidence
        return [
            p.page_number
            for p in self.pages
            if p.extraction_source == "ocr"
            and p.confidence is not None
            and p.confidence < threshold
        ]

    def low_index_blocks(self) -> list[OCRBlockStat]:
        threshold = settings.ocr_index_min_confidence
        return [
            b
            for b in self.blocks
            if b.extraction_source == "ocr"
            and b.confidence is not None
            and b.confidence < threshold
        ]

    def enforce_job_quality(self, *, document_type: str, total_page_count: int) -> str | None:
        """Return a low-quality tag detail instead of blocking ingest.

        Historically this raised OCRQualityInsufficientError and killed the
        whole job when too many OCR blocks/pages fell below the confidence
        threshold. Ingest is now tag-only: every document goes through and
        any quality concern is surfaced as metadata for review instead.
        """
        block_threshold = settings.ocr_block_job_min_confidence
        is_safety = document_type in SAFETY_DOCUMENT_TYPES

        ocr_blocks = [b for b in self.blocks if b.extraction_source == "ocr" and b.confidence is not None]
        if ocr_blocks:
            low_blocks = [b for b in ocr_blocks if b.confidence < block_threshold]
            fail_ratio = SAFETY_OCR_BLOCK_FAIL_RATIO if is_safety else 0.5
            if len(low_blocks) / len(ocr_blocks) > fail_ratio:
                return (
                    f"{len(low_blocks)}/{len(ocr_blocks)} OCR blocks below threshold "
                    f"({block_threshold}%) for {document_type}"
                )
            return None

        if not is_safety or total_page_count <= 0:
            return None

        ocr_pages = [p for p in self.pages if p.extraction_source == "ocr" and p.confidence is not None]
        if not ocr_pages:
            return None
        low = [p for p in ocr_pages if p.confidence < block_threshold]
        if len(low) / total_page_count > SAFETY_OCR_BLOCK_FAIL_RATIO:
            return (
                f"{len(low)}/{total_page_count} pages below OCR block threshold "
                f"({block_threshold}%) for {document_type}"
            )
        return None


def chunk_index_rejected(confidence: float | None, extraction_source: str) -> bool:
    """True when an OCR-derived chunk must not be embedded."""
    if extraction_source != "ocr" or confidence is None:
        return False
    return confidence < settings.ocr_index_min_confidence
