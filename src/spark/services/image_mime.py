from __future__ import annotations

from pathlib import Path

ALLOWED_IMAGE_MIMES: frozenset[str] = frozenset(
    {"image/jpeg", "image/png", "image/webp"}
)

_EXT_BY_MIME: dict[str, str] = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}

_MIME_BY_EXT: dict[str, str] = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}


def is_allowed_image_mime(mime: str) -> bool:
    return mime in ALLOWED_IMAGE_MIMES


def ext_for_image_mime(mime: str) -> str:
    return _EXT_BY_MIME.get(mime, ".jpg")


def guess_image_mime_from_name(filename: str) -> str | None:
    ext = Path(filename).suffix.lower()
    return _MIME_BY_EXT.get(ext)
