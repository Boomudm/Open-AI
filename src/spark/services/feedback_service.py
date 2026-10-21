from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, BinaryIO

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from spark.core.config import settings
from spark.core.security import Principal, accessible_factory_ids, can_access_factory
from spark.db.models.chat import ChatMessage, ChatSession
from spark.db.models.docs import Document
from spark.db.models.feedback import KnowledgeFeedback, KnowledgeFeedbackAttachment
from spark.db.models.org import Machine, User
from spark.services.document_access_service import can_access_document
from spark.services.image_mime import is_allowed_image_mime
from spark.storage import get_storage
from spark.storage.keys import feedback_photo_object_key, key_to_local_path

VALID_SOURCE_TYPES = frozenset({"document", "rag_answer", "rag_source"})
VALID_ISSUE_TYPES = frozenset(
    {"incorrect", "outdated", "missing_step", "unclear", "other"}
)
VALID_STATUSES = frozenset({"open", "triaged", "resolved", "wont_fix"})
TERMINAL_STATUSES = frozenset({"resolved", "wont_fix"})


def feedback_photo_path(
    *,
    factory_id: str,
    feedback_id: uuid.UUID,
    created_at: datetime,
    sort_order: int,
    mime: str,
) -> Path:
    key = feedback_photo_object_key(
        factory_id=factory_id,
        feedback_id=feedback_id,
        created_at=created_at,
        sort_order=sort_order,
        mime=mime,
    )
    return key_to_local_path(
        key,
        documents_dir=settings.documents_dir,
        machines_dir=settings.machines_dir,
        feedback_dir=settings.feedback_dir,
    )


async def save_feedback_photo(
    *,
    factory_id: str,
    feedback_id: uuid.UUID,
    created_at: datetime,
    sort_order: int,
    mime: str,
    stream: BinaryIO,
) -> str:
    key = feedback_photo_object_key(
        factory_id=factory_id,
        feedback_id=feedback_id,
        created_at=created_at,
        sort_order=sort_order,
        mime=mime,
    )
    storage = get_storage()
    return await storage.put_object(key, stream, content_type=mime)


async def delete_feedback_files(storage_uris: list[str]) -> None:
    storage = get_storage()
    for uri in storage_uris:
        try:
            await storage.delete(uri)
        except (ValueError, OSError):
            pass


def _parse_user_id(user_id: str | None) -> uuid.UUID | None:
    if not user_id:
        return None
    try:
        parsed = uuid.UUID(user_id)
    except ValueError:
        return None
    return parsed


async def _resolve_user_id(session: AsyncSession, user_id: str | None) -> uuid.UUID | None:
    parsed = _parse_user_id(user_id)
    if parsed is None:
        return None
    if await session.get(User, parsed) is not None:
        return parsed
    return None


def _can_list_inbox(p: Principal, factory_id: str) -> bool:
    if p.is_admin:
        return True
    return can_access_factory(p, factory_id, "write")


def _can_view_feedback(p: Principal, row: KnowledgeFeedback) -> bool:
    if p.is_admin:
        return True
    if can_access_factory(p, row.factory_id, "write"):
        return True
    uid = _parse_user_id(p.user_id)
    return uid is not None and row.created_by == uid


def _can_triage(p: Principal, row: KnowledgeFeedback) -> bool:
    if p.is_admin:
        return True
    return can_access_factory(p, row.factory_id, "write")


async def _validate_create_context(
    session: AsyncSession,
    p: Principal,
    *,
    factory_id: str,
    machine_id: str | None,
    doc_id: uuid.UUID | None,
    session_id: uuid.UUID | None,
    message_id: uuid.UUID | None,
) -> None:
    machine = None
    if machine_id:
        machine = await session.get(Machine, machine_id)
        if not machine:
            raise HTTPException(404, "machine not found")
        if machine.factory_id != factory_id:
            raise HTTPException(400, "machine factory mismatch")

    if doc_id:
        doc = await session.get(Document, doc_id)
        if not doc:
            raise HTTPException(404, "document not found")
        if not await can_access_document(session, p, doc):
            raise HTTPException(403, "no access to document")

    if session_id:
        chat_session = await session.get(ChatSession, session_id)
        if not chat_session:
            raise HTTPException(404, "chat session not found")
        if not p.is_admin:
            uid = _parse_user_id(p.user_id)
            if uid is None or chat_session.user_id != uid:
                raise HTTPException(403, "no access to chat session")

    if message_id:
        msg = await session.get(ChatMessage, message_id)
        if not msg:
            raise HTTPException(404, "chat message not found")
        if session_id and msg.session_id != session_id:
            raise HTTPException(400, "message session mismatch")
        if not p.is_admin:
            chat_session = await session.get(ChatSession, msg.session_id)
            if not chat_session:
                raise HTTPException(404, "chat session not found")
            uid = _parse_user_id(p.user_id)
            if uid is None or chat_session.user_id != uid:
                raise HTTPException(403, "no access to chat message")


def _infer_doc_from_sources(
    sources: list[Any] | None,
) -> tuple[uuid.UUID | None, int | None, str | None]:
    if not sources:
        return None, None, None
    for src in sources:
        if not isinstance(src, dict):
            continue
        raw_doc = src.get("doc_id")
        if not raw_doc:
            continue
        try:
            doc_uuid = uuid.UUID(str(raw_doc))
        except ValueError:
            continue
        page_raw = src.get("page")
        page_int: int | None = None
        if page_raw is not None:
            try:
                page_int = int(page_raw)
            except (TypeError, ValueError):
                page_int = None
        title = src.get("source_file") or src.get("title")
        return doc_uuid, page_int, str(title) if title else None
    return None, None, None


async def _build_feedback_context_snapshot(
    session: AsyncSession,
    message_id: uuid.UUID,
) -> dict[str, Any]:
    msg = await session.get(ChatMessage, message_id)
    if msg is None or msg.role != "assistant":
        return {}
    prior_user = (
        await session.execute(
            select(ChatMessage)
            .where(
                ChatMessage.session_id == msg.session_id,
                ChatMessage.role == "user",
                ChatMessage.created_at < msg.created_at,
            )
            .order_by(ChatMessage.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    return {
        "question": prior_user.content if prior_user else None,
        "answer": msg.content,
        "sources": msg.sources or [],
        "message_id": str(message_id),
    }


async def create_feedback(
    session: AsyncSession,
    p: Principal,
    *,
    factory_id: str,
    source_type: str,
    comment: str,
    machine_id: str | None = None,
    doc_id: uuid.UUID | None = None,
    page: int | None = None,
    session_id: uuid.UUID | None = None,
    message_id: uuid.UUID | None = None,
    issue_type: str | None = None,
    context: dict[str, Any] | None = None,
    photos: list[tuple[str, bytes]] | None = None,
) -> KnowledgeFeedback:
    if source_type not in VALID_SOURCE_TYPES:
        raise HTTPException(400, f"invalid source_type: {source_type}")
    if issue_type and issue_type not in VALID_ISSUE_TYPES:
        raise HTTPException(400, f"invalid issue_type: {issue_type}")
    comment = comment.strip()
    if not comment:
        raise HTTPException(400, "comment is required")
    if len(comment) > settings.max_feedback_comment_chars:
        raise HTTPException(400, "comment too long")

    photos = photos or []
    if len(photos) > settings.max_feedback_photos:
        raise HTTPException(400, "too many photos")

    await _validate_create_context(
        session,
        p,
        factory_id=factory_id,
        machine_id=machine_id,
        doc_id=doc_id,
        session_id=session_id,
        message_id=message_id,
    )

    if message_id and not context:
        context = await _build_feedback_context_snapshot(session, message_id)

    if doc_id is None and context:
        sources = context.get("sources") if isinstance(context, dict) else None
        inferred_doc, inferred_page, inferred_title = _infer_doc_from_sources(
            sources if isinstance(sources, list) else None
        )
        if inferred_doc is not None:
            doc_id = inferred_doc
            if page is None and inferred_page is not None:
                page = inferred_page
            if inferred_title and isinstance(context, dict):
                context.setdefault("doc_title", inferred_title)

    feedback_id = uuid.uuid4()
    created_by = await _resolve_user_id(session, p.user_id)
    created_at = datetime.now(UTC)

    row = KnowledgeFeedback(
        feedback_id=feedback_id,
        factory_id=factory_id,
        machine_id=machine_id,
        source_type=source_type,
        doc_id=doc_id,
        page=page,
        session_id=session_id,
        message_id=message_id,
        comment=comment,
        issue_type=issue_type,
        status="open",
        context=context,
        created_by=created_by,
    )
    session.add(row)
    await session.flush()

    for idx, (mime, raw) in enumerate(photos):
        if not is_allowed_image_mime(mime):
            raise HTTPException(400, f"unsupported image type: {mime}")
        if len(raw) > settings.max_feedback_photo_bytes:
            raise HTTPException(400, "photo too large")
        import io

        uri = await save_feedback_photo(
            factory_id=factory_id,
            feedback_id=feedback_id,
            created_at=created_at,
            sort_order=idx,
            mime=mime,
            stream=io.BytesIO(raw),
        )
        session.add(
            KnowledgeFeedbackAttachment(
                feedback_id=feedback_id,
                storage_uri=uri,
                mime_type=mime,
                sort_order=idx,
            )
        )

    await session.commit()
    await session.refresh(row)
    result = await get_feedback(session, p, feedback_id)
    assert result is not None
    return result


async def get_feedback(
    session: AsyncSession,
    p: Principal,
    feedback_id: uuid.UUID,
) -> KnowledgeFeedback | None:
    stmt = (
        select(KnowledgeFeedback)
        .where(KnowledgeFeedback.feedback_id == feedback_id)
        .options(selectinload(KnowledgeFeedback.attachments))
    )
    row = (await session.execute(stmt)).scalar_one_or_none()
    if not row:
        return None
    if not _can_view_feedback(p, row):
        raise HTTPException(403, "no access to feedback")
    return row


async def list_feedback(
    session: AsyncSession,
    p: Principal,
    *,
    status: str | None = None,
    factory_id: str | None = None,
    doc_id: uuid.UUID | None = None,
    machine_id: str | None = None,
    mine: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[KnowledgeFeedback], int]:
    if status and status not in VALID_STATUSES:
        raise HTTPException(400, f"invalid status: {status}")

    allowed = accessible_factory_ids(p)
    if allowed is not None and not allowed:
        return [], 0

    stmt = select(KnowledgeFeedback)
    count_stmt = select(func.count()).select_from(KnowledgeFeedback)

    if allowed is not None:
        stmt = stmt.where(KnowledgeFeedback.factory_id.in_(allowed))
        count_stmt = count_stmt.where(KnowledgeFeedback.factory_id.in_(allowed))

    if mine:
        uid = _parse_user_id(p.user_id)
        if uid is None:
            return [], 0
        stmt = stmt.where(KnowledgeFeedback.created_by == uid)
        count_stmt = count_stmt.where(KnowledgeFeedback.created_by == uid)
        if factory_id:
            if allowed is not None and factory_id not in allowed:
                raise HTTPException(403, f"no access to factory {factory_id}")
            if not can_access_factory(p, factory_id, "read"):
                raise HTTPException(403, f"no access to factory {factory_id}")
            stmt = stmt.where(KnowledgeFeedback.factory_id == factory_id)
            count_stmt = count_stmt.where(KnowledgeFeedback.factory_id == factory_id)
    elif factory_id:
        if allowed is not None and factory_id not in allowed:
            raise HTTPException(403, f"no access to factory {factory_id}")
        if not _can_list_inbox(p, factory_id):
            raise HTTPException(403, "inbox requires write access")
        stmt = stmt.where(KnowledgeFeedback.factory_id == factory_id)
        count_stmt = count_stmt.where(KnowledgeFeedback.factory_id == factory_id)
    elif not p.is_admin:
        write_factories = [
            fid for fid, lvl in p.factory_access.items() if lvl in ("write", "admin")
        ]
        if not write_factories:
            raise HTTPException(403, "inbox requires write access")
        stmt = stmt.where(KnowledgeFeedback.factory_id.in_(write_factories))
        count_stmt = count_stmt.where(KnowledgeFeedback.factory_id.in_(write_factories))

    if status:
        stmt = stmt.where(KnowledgeFeedback.status == status)
        count_stmt = count_stmt.where(KnowledgeFeedback.status == status)
    if doc_id:
        stmt = stmt.where(KnowledgeFeedback.doc_id == doc_id)
        count_stmt = count_stmt.where(KnowledgeFeedback.doc_id == doc_id)
    if machine_id:
        stmt = stmt.where(KnowledgeFeedback.machine_id == machine_id)
        count_stmt = count_stmt.where(KnowledgeFeedback.machine_id == machine_id)

    total = int((await session.execute(count_stmt)).scalar_one())
    if limit == 0:
        return [], total

    stmt = (
        stmt.options(selectinload(KnowledgeFeedback.attachments))
        .order_by(KnowledgeFeedback.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    rows = list((await session.execute(stmt)).scalars().all())
    return rows, total


async def patch_feedback(
    session: AsyncSession,
    p: Principal,
    feedback_id: uuid.UUID,
    *,
    status: str | None = None,
    resolution_note: str | None = None,
) -> KnowledgeFeedback:
    row = await get_feedback(session, p, feedback_id)
    if not row:
        raise HTTPException(404, "feedback not found")
    if not _can_triage(p, row):
        raise HTTPException(403, "no permission to triage feedback")

    if status:
        if status not in VALID_STATUSES:
            raise HTTPException(400, f"invalid status: {status}")
        row.status = status
        if status in TERMINAL_STATUSES:
            row.resolved_by = await _resolve_user_id(session, p.user_id)
            row.resolved_at = datetime.now(UTC)
        elif row.status not in TERMINAL_STATUSES:
            row.resolved_by = None
            row.resolved_at = None

    if resolution_note is not None:
        row.resolution_note = resolution_note.strip() or None

    await session.commit()
    refreshed = await get_feedback(session, p, feedback_id)
    assert refreshed is not None
    return refreshed


def parse_context_json(raw: str | None) -> dict[str, Any] | None:
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(400, "invalid context JSON") from exc
    if not isinstance(parsed, dict):
        raise HTTPException(400, "context must be a JSON object")
    return parsed
