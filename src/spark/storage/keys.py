from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from uuid import UUID

from spark.services.image_mime import ext_for_image_mime

_CHAT_PDF_MIME = "application/pdf"

_KEY_UNSAFE = re.compile(r"[/\\]+")
_KEY_SPECIAL = re.compile(r"[^\w.\-]+")


def sanitize_segment(value: str | None, *, fallback: str = "_unknown") -> str:
    if value is None or not str(value).strip():
        return fallback
    cleaned = _KEY_UNSAFE.sub("-", str(value).strip())
    cleaned = _KEY_SPECIAL.sub("-", cleaned)
    cleaned = cleaned.strip("-")
    return cleaned or fallback


def _require_segment(value: str | None, field: str) -> str:
    if value is None or not str(value).strip():
        raise ValueError(f"{field} is required for storage object key")
    segment = sanitize_segment(value, fallback="")
    if not segment:
        raise ValueError(f"{field} is required for storage object key")
    return segment


def _safe_ext(filename: str) -> str:
    suffix = Path(filename).suffix
    return suffix if suffix else ".bin"


def document_object_key(
    *,
    factory_id: str,
    document_type: str,
    machine_id: str | None,
    doc_id: UUID,
    filename: str,
) -> str:
    factory = _require_segment(factory_id, "factory_id")
    doc_type = _require_segment(document_type, "document_type")
    machine = sanitize_segment(machine_id, fallback="_general")
    ext = _safe_ext(filename)
    return f"documents/{factory}/{doc_type}/{machine}/{doc_id}/original{ext}"


def machine_image_object_key(*, factory_id: str, machine_id: str, mime: str) -> str:
    factory = _require_segment(factory_id, "factory_id")
    machine = _require_segment(machine_id, "machine_id")
    ext = ext_for_image_mime(mime)
    return f"machines/{factory}/{machine}/cover{ext}"


def profile_image_object_key(*, user_id: UUID, mime: str) -> str:
    ext = ext_for_image_mime(mime)
    return f"profiles/{user_id}/avatar{ext}"


def _ext_for_chat_attachment_mime(mime: str) -> str:
    if mime == _CHAT_PDF_MIME:
        return ".pdf"
    return ext_for_image_mime(mime)


def chat_attachment_object_key(
    *,
    factory_id: str,
    session_id: UUID,
    message_id: UUID,
    sort_order: int,
    mime: str,
) -> str:
    factory = _require_segment(factory_id, "factory_id")
    session = str(session_id)
    message = str(message_id)
    ext = _ext_for_chat_attachment_mime(mime)
    return f"chat/{factory}/{session}/{message}/attachment-{sort_order + 1}{ext}"


def feedback_photo_object_key(
    *,
    factory_id: str,
    feedback_id: UUID,
    created_at: datetime,
    sort_order: int,
    mime: str,
) -> str:
    factory = _require_segment(factory_id, "factory_id")
    year_month = created_at.strftime("%Y-%m")
    ext = ext_for_image_mime(mime)
    return f"feedback/{factory}/{year_month}/{feedback_id}/photo-{sort_order + 1}{ext}"


def key_to_local_path(
    key: str,
    *,
    documents_dir: Path,
    machines_dir: Path,
    feedback_dir: Path,
    profile_images_dir: Path | None = None,
    chat_attachments_dir: Path | None = None,
) -> Path:
    if key.startswith("documents/"):
        return documents_dir / key.removeprefix("documents/")
    if key.startswith("machines/"):
        return machines_dir / key.removeprefix("machines/")
    if key.startswith("profiles/"):
        if profile_images_dir is None:
            raise ValueError("profile_images_dir is required for profiles/ keys")
        return profile_images_dir / key.removeprefix("profiles/")
    if key.startswith("feedback/"):
        return feedback_dir / key.removeprefix("feedback/")
    if key.startswith("chat/"):
        if chat_attachments_dir is None:
            raise ValueError("chat_attachments_dir is required for chat/ keys")
        return chat_attachments_dir / key.removeprefix("chat/")
    raise ValueError(f"unsupported object key prefix: {key}")
