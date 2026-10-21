from __future__ import annotations

import asyncio
import io
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from fastapi import HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from spark.core.config import settings
from spark.core.logging import get_logger
from spark.db.models.chat import ChatMessageAttachment
from spark.ingestion.parsers.image_ocr_parser import OCRUnavailableError, _ocr_image_file, _ocr_pdf_extract_pages
from spark.ingestion.parsers.pdf_parser import _extract_pages
from spark.services.image_mime import guess_image_mime_from_name, is_allowed_image_mime
from spark.storage import get_storage
from spark.storage.keys import chat_attachment_object_key

log = get_logger(__name__)

ALLOWED_CHAT_ATTACHMENT_MIMES: frozenset[str] = frozenset(
    {"image/jpeg", "image/png", "image/webp", "application/pdf"}
)
CHAT_PDF_MIME = "application/pdf"


class AttachmentExtractError(Exception):
    """Raised when attachment text extraction fails."""

    def __init__(self, filename: str, reason: str) -> None:
        self.filename = filename
        self.reason = reason
        super().__init__(f"cannot read attachment: {filename} — {reason}")


@dataclass(frozen=True)
class PreparedAttachment:
    filename: str
    mime_type: str
    file_size_bytes: int
    storage_uri: str
    extracted_text: str
    sort_order: int


def resolve_attachment_mime(filename: str, content_type: str | None) -> str | None:
    mime = (content_type or "").split(";")[0].strip().lower()
    if mime in ALLOWED_CHAT_ATTACHMENT_MIMES:
        return mime
    guessed = guess_image_mime_from_name(filename)
    if guessed and guessed in ALLOWED_CHAT_ATTACHMENT_MIMES:
        return guessed
    if filename.lower().endswith(".pdf"):
        return CHAT_PDF_MIME
    return None


def validate_attachment_uploads(files: list[UploadFile]) -> None:
    if not files:
        raise HTTPException(422, "at least one file is required for multipart ask")
    if len(files) > settings.max_chat_attachments_per_message:
        raise HTTPException(
            422,
            f"too many attachments (max {settings.max_chat_attachments_per_message})",
        )


async def read_upload_bytes(upload: UploadFile) -> tuple[bytes, str, str]:
    filename = (upload.filename or "attachment").strip() or "attachment"
    mime = resolve_attachment_mime(filename, upload.content_type)
    if mime is None:
        raise HTTPException(
            422,
            f"unsupported file type: {filename} (allowed: JPEG, PNG, WebP, PDF)",
        )
    from spark.api.upload_utils import read_upload_bounded

    try:
        data = await read_upload_bounded(upload, settings.max_chat_attachment_bytes)
    except HTTPException as exc:
        if exc.status_code == 413:
            raise HTTPException(
                422,
                f"file too large: {filename} (max {settings.max_chat_attachment_bytes} bytes)",
            ) from exc
        raise
    if not data:
        raise HTTPException(422, f"empty file: {filename}")
    return data, filename, mime


async def save_attachment(
    *,
    factory_id: str,
    session_id: uuid.UUID,
    message_id: uuid.UUID,
    sort_order: int,
    mime: str,
    stream: BinaryIO,
) -> str:
    key = chat_attachment_object_key(
        factory_id=factory_id,
        session_id=session_id,
        message_id=message_id,
        sort_order=sort_order,
        mime=mime,
    )
    storage = get_storage()
    return await storage.put_object(key, stream, content_type=mime)


def _truncate_extracted(text: str) -> str:
    limit = settings.max_chat_attachment_extract_chars
    if len(text) <= limit:
        return text
    return text[:limit]


def _extract_pdf_text(path: Path, filename: str) -> str:
    try:
        _, pages = _extract_pages(path)
    except Exception as exc:
        raise AttachmentExtractError(filename, f"cannot read PDF: {exc}") from exc

    parts: list[str] = []
    empty_pages: list[int] = []
    for page_num, page_text, _ in pages:
        if page_text.strip():
            parts.append(f"[หน้า {page_num}]\n{page_text.strip()}")
        else:
            empty_pages.append(page_num)

    if parts:
        return _truncate_extracted("\n\n".join(parts))

    try:
        ocr_result = _ocr_pdf_extract_pages(path)
    except OCRUnavailableError as exc:
        raise AttachmentExtractError(filename, str(exc)) from exc
    except Exception as exc:
        raise AttachmentExtractError(filename, f"OCR failed: {exc}") from exc

    ocr_parts = [
        f"[หน้า {page.page_number or idx}]\n{page.text.strip()}"
        for idx, page in enumerate(ocr_result.pages, start=1)
        if page.text.strip()
    ]
    if not ocr_parts:
        raise AttachmentExtractError(filename, "OCR returned no text")
    return _truncate_extracted("\n\n".join(ocr_parts))


def _extract_image_text(path: Path, filename: str) -> str:
    try:
        result = _ocr_image_file(path)
    except OCRUnavailableError as exc:
        raise AttachmentExtractError(filename, str(exc)) from exc
    except Exception as exc:
        raise AttachmentExtractError(filename, f"OCR failed: {exc}") from exc

    text = result.text.strip()
    if not text:
        raise AttachmentExtractError(filename, "OCR returned no text")
    return _truncate_extracted(text)


async def extract_attachment_text(storage_uri: str, filename: str, mime: str) -> str:
    storage = get_storage()
    loop = asyncio.get_running_loop()

    def _run() -> str:
        with storage.materialize_local(storage_uri) as path:
            if mime == CHAT_PDF_MIME:
                return _extract_pdf_text(path, filename)
            if is_allowed_image_mime(mime):
                return _extract_image_text(path, filename)
            raise AttachmentExtractError(filename, f"unsupported mime type: {mime}")

    return await loop.run_in_executor(None, _run)


def build_attachment_context(attachments: list[PreparedAttachment]) -> str:
    blocks: list[str] = []
    for att in attachments:
        blocks.append(f"[แนบไฟล์: {att.filename}]\n{att.extracted_text}")
    return "\n\n".join(blocks)


async def cleanup_storage_uris(uris: list[str]) -> None:
    if not uris:
        return
    storage = get_storage()
    for uri in uris:
        try:
            await storage.delete(uri)
        except (ValueError, OSError) as exc:
            log.warning("chat_attachment_cleanup_failed", uri=uri, error=str(exc)[:200])


async def delete_session_attachment_files(db: AsyncSession, session_id: uuid.UUID) -> None:
    rows = (
        await db.execute(
            select(ChatMessageAttachment.storage_uri).where(
                ChatMessageAttachment.session_id == session_id
            )
        )
    ).scalars().all()
    await cleanup_storage_uris(list(rows))


async def prepare_attachments(
    *,
    factory_id: str,
    session_id: uuid.UUID,
    message_id: uuid.UUID,
    uploads: list[tuple[bytes, str, str]],
) -> tuple[list[PreparedAttachment], list[str]]:
    prepared: list[PreparedAttachment] = []
    saved_uris: list[str] = []
    try:
        for sort_order, (data, filename, mime) in enumerate(uploads):
            stream = io.BytesIO(data)
            uri = await save_attachment(
                factory_id=factory_id,
                session_id=session_id,
                message_id=message_id,
                sort_order=sort_order,
                mime=mime,
                stream=stream,
            )
            saved_uris.append(uri)
            extracted = await extract_attachment_text(uri, filename, mime)
            prepared.append(
                PreparedAttachment(
                    filename=filename,
                    mime_type=mime,
                    file_size_bytes=len(data),
                    storage_uri=uri,
                    extracted_text=extracted,
                    sort_order=sort_order,
                )
            )
        return prepared, saved_uris
    except Exception:
        await cleanup_storage_uris(saved_uris)
        raise
