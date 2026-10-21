from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from spark.api.openapi_responses import READ_ERRORS, WRITE_ERRORS
from spark.api.upload_utils import read_upload_bounded
from spark.core.config import settings
from spark.core.database import get_session
from spark.core.security import enforce_factory_access, get_principal
from spark.schemas.feedback import FeedbackCountOut, FeedbackOut, FeedbackPatch
from spark.schemas.pagination import PaginatedResponse
from spark.services.feedback_service import (
    create_feedback,
    get_feedback,
    list_feedback,
    parse_context_json,
    patch_feedback,
)
from spark.services.image_mime import guess_image_mime_from_name, is_allowed_image_mime
from spark.storage import get_storage
from spark.storage.resolve import open_storage_object_async

router = APIRouter(prefix="/feedback", tags=["Feedback"])


def _attachment_url(feedback_id: uuid.UUID, sort_order: int) -> str:
    return f"/api/v1/feedback/{feedback_id}/attachments/{sort_order}"


def _to_out(row) -> FeedbackOut:
    from spark.schemas.feedback import FeedbackAttachmentOut

    return FeedbackOut(
        feedback_id=row.feedback_id,
        factory_id=row.factory_id,
        machine_id=row.machine_id,
        source_type=row.source_type,
        doc_id=row.doc_id,
        page=row.page,
        session_id=row.session_id,
        message_id=row.message_id,
        comment=row.comment,
        issue_type=row.issue_type,
        status=row.status,
        context=row.context,
        resolution_note=row.resolution_note,
        resolved_by=row.resolved_by,
        resolved_at=row.resolved_at,
        created_by=row.created_by,
        created_at=row.created_at,
        attachments=[
            FeedbackAttachmentOut(
                attachment_id=a.attachment_id,
                sort_order=a.sort_order,
                mime_type=a.mime_type,
                url=_attachment_url(row.feedback_id, a.sort_order),
            )
            for a in sorted(row.attachments, key=lambda x: x.sort_order)
        ],
    )


@router.post("", response_model=FeedbackOut, status_code=201, responses=READ_ERRORS)
async def submit_feedback(
    request: Request,
    factory_id: str = Form(...),
    source_type: str = Form(...),
    comment: str = Form(...),
    machine_id: str | None = Form(None),
    doc_id: str | None = Form(None),
    page: int | None = Form(None),
    session_id: str | None = Form(None),
    message_id: str | None = Form(None),
    issue_type: str | None = Form(None),
    context: str | None = Form(None),
    photos: list[UploadFile] = File(default=[]),
    session: AsyncSession = Depends(get_session),
):
    p = get_principal(request)
    enforce_factory_access(p, factory_id, "read")

    try:
        parsed_doc_id = uuid.UUID(doc_id) if doc_id else None
    except ValueError:
        raise HTTPException(422, "invalid doc_id format")
    try:
        parsed_session_id = uuid.UUID(session_id) if session_id else None
    except ValueError:
        raise HTTPException(422, "invalid session_id format")
    try:
        parsed_message_id = uuid.UUID(message_id) if message_id else None
    except ValueError:
        raise HTTPException(422, "invalid message_id format")
    parsed_context = parse_context_json(context)

    photo_payload: list[tuple[str, bytes]] = []
    for upload in photos:
        if not upload.filename:
            continue
        raw = await read_upload_bounded(upload, settings.max_upload_bytes)
        if not raw:
            continue
        mime = upload.content_type or ""
        if not is_allowed_image_mime(mime):
            guessed = guess_image_mime_from_name(upload.filename)
            mime = guessed or mime
        if not is_allowed_image_mime(mime):
            raise HTTPException(400, "unsupported image type")
        photo_payload.append((mime, raw))

    row = await create_feedback(
        session,
        p,
        factory_id=factory_id,
        source_type=source_type,
        comment=comment,
        machine_id=machine_id or None,
        doc_id=parsed_doc_id,
        page=page,
        session_id=parsed_session_id,
        message_id=parsed_message_id,
        issue_type=issue_type or None,
        context=parsed_context,
        photos=photo_payload,
    )
    return _to_out(row)


@router.get("", response_model=PaginatedResponse[FeedbackOut], responses=READ_ERRORS)
async def list_feedback_inbox(
    request: Request,
    status: str | None = None,
    factory_id: str | None = None,
    doc_id: uuid.UUID | None = None,
    machine_id: str | None = None,
    mine: bool = Query(False),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=0, le=200),
    session: AsyncSession = Depends(get_session),
):
    p = get_principal(request)
    if factory_id and not mine:
        enforce_factory_access(p, factory_id, "write")

    offset = (page - 1) * page_size if page_size else 0
    rows, total = await list_feedback(
        session,
        p,
        status=status,
        factory_id=factory_id,
        doc_id=doc_id,
        machine_id=machine_id,
        mine=mine,
        limit=page_size,
        offset=offset,
    )
    return PaginatedResponse(
        items=[_to_out(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/count", response_model=FeedbackCountOut, responses=READ_ERRORS)
async def feedback_open_count(
    request: Request,
    status: str | None = Query("open"),
    factory_id: str | None = None,
    session: AsyncSession = Depends(get_session),
):
    p = get_principal(request)
    if factory_id:
        enforce_factory_access(p, factory_id, "write")

    _, total = await list_feedback(
        session,
        p,
        status=status,
        factory_id=factory_id,
        limit=0,
        offset=0,
    )
    return FeedbackCountOut(count=total)


@router.get("/{feedback_id}", response_model=FeedbackOut, responses=READ_ERRORS)
async def get_feedback_detail(
    feedback_id: uuid.UUID,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    p = get_principal(request)
    row = await get_feedback(session, p, feedback_id)
    if not row:
        raise HTTPException(404, "feedback not found")
    return _to_out(row)


@router.patch("/{feedback_id}", response_model=FeedbackOut, responses=WRITE_ERRORS)
async def update_feedback(
    feedback_id: uuid.UUID,
    body: FeedbackPatch,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    p = get_principal(request)
    row = await patch_feedback(
        session,
        p,
        feedback_id,
        status=body.status,
        resolution_note=body.resolution_note,
    )
    return _to_out(row)


@router.get("/{feedback_id}/attachments/{sort_order}", responses=READ_ERRORS)
async def stream_feedback_attachment(
    feedback_id: uuid.UUID,
    sort_order: int,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    p = get_principal(request)
    row = await get_feedback(session, p, feedback_id)
    if not row:
        raise HTTPException(404, "feedback not found")

    attachment = next((a for a in row.attachments if a.sort_order == sort_order), None)
    if not attachment:
        raise HTTPException(404, "attachment not found")

    storage = get_storage()
    if not await storage.exists(attachment.storage_uri):
        raise HTTPException(404, "attachment file not found")

    return StreamingResponse(
        open_storage_object_async(attachment.storage_uri),
        media_type=attachment.mime_type,
    )
