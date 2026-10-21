from __future__ import annotations

import mimetypes
from pathlib import Path

import filetype

# Python's stdlib mimetypes table (and this container's /etc/mime.types, if
# any) never learned the Office Open XML formats on this system — .xlsx,
# .docx and .pptx all guess_type() to (None, None) here even though .xls,
# .doc and .ppt work fine. guess_mime_type() then fell back to
# "application/octet-stream", which never matches the correctly magic-byte
# sniffed OOXML mime below, so every .xlsx/.docx/.pptx upload was rejected
# as a false "MIME mismatch" regardless of content. Register them explicitly
# so validation doesn't depend on the host's mime database being complete.
mimetypes.add_type(
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", ".xlsx"
)
mimetypes.add_type(
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document", ".docx"
)
mimetypes.add_type(
    "application/vnd.openxmlformats-officedocument.presentationml.presentation", ".pptx"
)

ALLOWED_MIME_PREFIXES = (
    "application/pdf",
    "application/vnd.openxmlformats-",
    "application/vnd.ms-",
    "application/msword",
    "application/json",
    "text/",
    "image/",
)

DEFAULT_MIME = "application/octet-stream"

_BINARY_EXTENSION_MAGIC: dict[str, tuple[bytes, ...]] = {
    ".pdf": (b"%PDF-",),
    ".docx": (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"),
    ".xlsx": (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"),
    ".pptx": (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"),
    ".doc": (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1",),
    ".xls": (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1",),
    ".ppt": (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1",),
}

# Declared MIME may differ slightly from magic-byte sniff (aliases).
_MIME_COMPATIBLE: dict[str, frozenset[str]] = {
    "application/pdf": frozenset({"application/pdf", "application/x-pdf"}),
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": frozenset(
        {
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/zip",
        }
    ),
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": frozenset(
        {
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "application/zip",
        }
    ),
    "application/vnd.ms-excel": frozenset({"application/vnd.ms-excel", "application/x-ole-storage"}),
}


def guess_mime_type(filename: str) -> str:
    mime, _ = mimetypes.guess_type(filename)
    return mime or DEFAULT_MIME


def sniff_mime_type(raw_bytes: bytes) -> str | None:
    if not raw_bytes:
        return None
    kind = filetype.guess(raw_bytes)
    return kind.mime if kind else None


def _mime_compatible(declared: str, sniffed: str) -> bool:
    if declared == sniffed:
        return True
    allowed = _MIME_COMPATIBLE.get(declared)
    if allowed and sniffed in allowed:
        return True
    allowed_sniff = _MIME_COMPATIBLE.get(sniffed)
    if allowed_sniff and declared in allowed_sniff:
        return True
    return False


def is_allowed_mime(mime: str) -> bool:
    if not mime:
        return False
    if mime == DEFAULT_MIME:
        return False
    return any(mime.startswith(prefix) for prefix in ALLOWED_MIME_PREFIXES)


def validate_upload_mime(filename: str, raw_bytes: bytes) -> str:
    """Return effective MIME after magic-byte cross-check."""
    declared = guess_mime_type(filename)
    sniffed = sniff_mime_type(raw_bytes)
    suffix = Path(filename or "").suffix.lower()
    required_magic = _BINARY_EXTENSION_MAGIC.get(suffix)
    if required_magic and not raw_bytes.startswith(required_magic):
        raise ValueError(f"MIME mismatch: {suffix} file does not have the expected file signature")
    if sniffed and not _mime_compatible(declared, sniffed):
        raise ValueError(
            f"MIME mismatch: filename suggests {declared}, content sniffed as {sniffed}"
        )
    effective = sniffed or declared
    if not is_allowed_mime(effective):
        raise ValueError(f"file type not allowed: {effective}")
    return effective


def resolve_document_mime(
    *,
    mime_type: str | None,
    original_filename: str | None,
    source_file: str | None,
) -> str:
    """Use stored mime or guess from filename (legacy rows often have mime_type=NULL)."""
    if mime_type and is_allowed_mime(mime_type):
        return mime_type
    for name in (original_filename, source_file):
        if not name:
            continue
        guessed = guess_mime_type(name)
        if is_allowed_mime(guessed):
            return guessed
    return mime_type or DEFAULT_MIME
