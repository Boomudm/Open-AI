from __future__ import annotations

import io
from pathlib import Path

from spark.core.logging import get_logger
from spark.ingestion.config_loader import list_document_types

log = get_logger(__name__)

FILENAME_HINTS = {
    "manual": "machine_manual",
    "ma001": "machine_manual",
    "sop": "sop",
    "spec": "datasheet",
    "datasheet": "datasheet",
    "iso": "iso_certificate",
    "nearmiss": "near_miss",
    "training": "training_note",
    # io_mapping hints checked first: "mapping_diagram.pdf" (a real filename in
    # use) contains both "mapping" and "diagram" — first-match-wins dict order
    # must resolve it to the more specific io_mapping type, not the generic
    # "diagram" drawing hint.
    "mapping": "io_mapping",
    "io_map": "io_mapping",
    "symlink": "io_mapping",
    "wiring": "drawing",
    "diagram": "drawing",
    "schematic": "drawing",
}

# Header phrases that identify an I/O mapping sheet regardless of filename —
# real factory exports (PLC symlink tables) rarely have predictable names.
# Checked against the first few rows/first page of the actual file content.
_CONTENT_SIGNATURE_HINTS: dict[str, tuple[str, ...]] = {
    "io_mapping": ("symbolic link name", "connected to (hardware ports)"),
}


def resolve_document_type(
    filename: str, override: str | None = None, *, content: bytes | None = None
) -> str | None:
    if override:
        return override
    lower = filename.lower()
    known = set(list_document_types())
    for hint, doc_type in FILENAME_HINTS.items():
        if hint in lower and doc_type in known:
            return doc_type
    if content:
        sniffed = detect_by_content_signature(Path(filename), content)
        if sniffed and sniffed in known:
            return sniffed
    if "knowledge_document" in known and detect_parser_for_path(Path(filename)):
        return "knowledge_document"
    return None


def _sniff_text(path: Path, content: bytes) -> str:
    """Best-effort, cheap text peek used only for content-signature sniffing."""
    ext = path.suffix.lower()
    try:
        if ext in (".xlsx", ".xls"):
            import pandas as pd

            df = pd.read_excel(io.BytesIO(content), sheet_name=0, header=None, nrows=3, dtype=str)
            return " ".join(str(v) for v in df.to_numpy().flatten() if v is not None)
        if ext == ".pdf":
            import pdfplumber

            with pdfplumber.open(io.BytesIO(content)) as pdf:
                if not pdf.pages:
                    return ""
                return pdf.pages[0].extract_text() or ""
        if ext in (".txt", ".md", ".csv"):
            return content[:4096].decode("utf-8", errors="ignore")
    except Exception as exc:  # noqa: BLE001 — sniffing is best-effort, never blocks upload
        log.debug("document_type_content_sniff_failed", file=str(path), error=str(exc)[:200])
    return ""


def detect_by_content_signature(path: Path, content: bytes) -> str | None:
    """Identify a document type from its actual content, independent of filename."""
    text = _sniff_text(path, content).lower()
    if not text:
        return None
    for doc_type, phrases in _CONTENT_SIGNATURE_HINTS.items():
        if all(phrase in text for phrase in phrases):
            return doc_type
    return None


def detect_parser_for_path(path: Path) -> str | None:
    ext = path.suffix.lower()
    if ext == ".pdf":
        return "pdf"
    if ext in (".xlsx", ".xls"):
        return "excel"
    if ext in (".docx", ".doc"):
        return "word"
    if ext in (".png", ".jpg", ".jpeg", ".tiff", ".bmp"):
        return "image_ocr"
    if ext == ".json":
        return "json"
    if ext in (".txt", ".md", ".csv"):
        return "text"
    return None
