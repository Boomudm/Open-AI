from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from spark.api.openapi_responses import READ_ERRORS, WRITE_ERRORS
from spark.core.database import AsyncSessionLocal, get_session
from spark.core.security import enforce_factory_access, enforce_rag_filter_access, get_principal
from spark.db.models.chat import ChatMessage, ChatMessageAttachment, ChatSession
from spark.schemas.openapi_examples import CHAT_SESSION_CREATE, CHAT_SESSION_OUT
from spark.schemas.pagination import PaginatedResponse
from spark.schemas.rag import AskRequest, AskResponse, RAGFilterModel
from spark.services.chat_attachment_service import (
    AttachmentExtractError,
    cleanup_storage_uris,
    delete_session_attachment_files,
    prepare_attachments,
    read_upload_bytes,
    validate_attachment_uploads,
)
from spark.services.chat_session_access import (
    chat_session_factory_clause,
    chat_session_unbound_factory_clause,
    chat_owner_clause,
    enforce_or_bind_session_factory,
    require_owned_session,
    resolve_chat_owner_id,
    session_factory_id,
)
from spark.services.session_title_service import DEFAULT_TITLES
from spark.services.chat_ask_dedupe import get_recent_ask, remember_ask
from spark.storage import get_storage
from spark.storage.resolve import open_storage_object_async

router = APIRouter(prefix="/chat", tags=["Chat"])

_MSG_COUNT = (
    select(func.count())
    .select_from(ChatMessage)
    .where(ChatMessage.session_id == ChatSession.session_id)
    .correlate(ChatSession)
    .scalar_subquery()
)


def _sidebar_visible_clause(*, include_session_id: UUID | None):
    has_custom_title = and_(
        ChatSession.title.isnot(None),
        func.trim(ChatSession.title) != "",
        func.lower(func.trim(ChatSession.title)).notin_(list(DEFAULT_TITLES)),
    )
    visible = or_(ChatSession.pinned.is_(True), _MSG_COUNT > 0, has_custom_title)
    if include_session_id is not None:
        visible = or_(visible, ChatSession.session_id == include_session_id)
    return visible


def _factory_session_list_clause(factory_id: str, include_session_id: UUID | None):
    exact_factory = chat_session_factory_clause(factory_id)
    if include_session_id is None:
        return exact_factory
    return or_(
        exact_factory,
        and_(
            ChatSession.session_id == include_session_id,
            chat_session_unbound_factory_clause(),
        ),
    )


class CreateSessionRequest(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [CHAT_SESSION_CREATE]})

    title: str | None = Field(None, examples=["Demo MC-001 session"])
    factory_id: str | None = Field(None, min_length=1, max_length=64)


class UpdateSessionRequest(BaseModel):
    title: str | None = Field(None, max_length=200)
    pinned: bool | None = None


class SessionOut(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [CHAT_SESSION_OUT]})

    session_id: UUID
    title: str | None
    pinned: bool = False
    context: dict | None = None


class ChatCapabilitiesOut(BaseModel):
    llm_profile: str
    llm_model: str
    top_k_fast: int = 6
    top_k_advanced: int = 10
    question_max_length: int = 3000


class SessionListOut(BaseModel):
    session_id: UUID
    title: str | None
    pinned: bool
    message_count: int = 0
    created_at: str
    updated_at: str
    context: dict | None = None
    factory_id: str | None = None


class ChatAttachmentOut(BaseModel):
    filename: str
    mime_type: str
    url: str
    sort_order: int


class ChatMessageOut(BaseModel):
    message_id: UUID
    role: str
    content: str
    sources: list | None = None
    confidence_tier: str | None = None
    cache_hit: bool = False
    verified_at: str | None = None
    created_at: str
    attachments: list[ChatAttachmentOut] = Field(default_factory=list)


def _attachment_url(session_id: UUID, message_id: UUID, sort_order: int) -> str:
    return (
        f"/api/v1/chat/{session_id}/messages/{message_id}/attachments/{sort_order}"
    )


def _message_out(session_id: UUID, message: ChatMessage) -> ChatMessageOut:
    attachments = [
        ChatAttachmentOut(
            filename=att.original_filename,
            mime_type=att.mime_type,
            url=_attachment_url(session_id, message.message_id, att.sort_order),
            sort_order=att.sort_order,
        )
        for att in sorted(message.attachments or [], key=lambda row: row.sort_order)
    ]
    return ChatMessageOut(
        message_id=message.message_id,
        role=message.role,
        content=message.content,
        sources=message.sources,
        confidence_tier=message.confidence_tier,
        cache_hit=bool(message.cache_hit),
        verified_at=message.verified_at.isoformat() if message.verified_at else None,
        created_at=message.created_at.isoformat() if message.created_at else "",
        attachments=attachments,
    )


def _resolve_factory_id(merged_filter, session_context: dict | None) -> str:
    ctx = session_context or {}
    factory_id = getattr(merged_filter, "factory_id", None) or ctx.get("factory_id")
    if not factory_id or not str(factory_id).strip():
        raise HTTPException(422, "factory_id is required to attach files")
    return str(factory_id).strip()


@router.get("/capabilities", response_model=ChatCapabilitiesOut, responses=READ_ERRORS)
async def chat_capabilities() -> ChatCapabilitiesOut:
    from spark.core.config import settings as app_settings
    from spark.core.llm_profile import load_llm_profile

    profile = load_llm_profile()
    tuning = profile.get("tuning") if isinstance(profile.get("tuning"), dict) else {}
    top_k_default = int(tuning.get("top_k_default") or 6)
    return ChatCapabilitiesOut(
        llm_profile=app_settings.llm_profile,
        llm_model=str(profile.get("llm_model") or app_settings.ollama_llm_model),
        top_k_fast=max(1, min(20, top_k_default)),
        top_k_advanced=max(1, min(20, top_k_default + 4)),
        question_max_length=app_settings.question_max_length,
    )


@router.get("/sessions", response_model=PaginatedResponse[SessionListOut], responses=READ_ERRORS)
async def list_sessions(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    for_sidebar: bool = Query(False, description="Hide orphan empty default-titled sessions"),
    include_session_id: UUID | None = Query(None, description="Always include this session (e.g. active draft)"),
    factory_id: str | None = Query(None, min_length=1, max_length=64),
    session: AsyncSession = Depends(get_session),
):
    p = get_principal(request)
    owner_id = await resolve_chat_owner_id(session, p)
    owner = chat_owner_clause(owner_id)
    normalized_factory_id = factory_id.strip() if factory_id else None
    if normalized_factory_id:
        enforce_factory_access(p, normalized_factory_id, "read")
    base = select(ChatSession).where(owner)
    if normalized_factory_id:
        base = base.where(
            _factory_session_list_clause(normalized_factory_id, include_session_id)
        )
    if for_sidebar:
        base = base.where(_sidebar_visible_clause(include_session_id=include_session_id))
    count_stmt = select(func.count()).select_from(base.subquery())
    total = int((await session.execute(count_stmt)).scalar_one())
    offset = (page - 1) * page_size
    stmt = select(ChatSession, _MSG_COUNT.label("message_count")).where(owner)
    if normalized_factory_id:
        stmt = stmt.where(
            _factory_session_list_clause(normalized_factory_id, include_session_id)
        )
    if for_sidebar:
        stmt = stmt.where(_sidebar_visible_clause(include_session_id=include_session_id))
    stmt = stmt.order_by(
        ChatSession.pinned.desc(),
        ChatSession.pinned_at.desc().nulls_last(),
        ChatSession.updated_at.desc(),
    ).offset(offset).limit(page_size)
    rows = (await session.execute(stmt)).all()
    items = [
        SessionListOut(
            session_id=s.session_id,
            title=s.title,
            pinned=bool(s.pinned),
            message_count=int(message_count or 0),
            created_at=s.created_at.isoformat() if s.created_at else "",
            updated_at=s.updated_at.isoformat() if s.updated_at else "",
            context=s.context,
            factory_id=session_factory_id(s),
        )
        for s, message_count in rows
    ]
    return PaginatedResponse(items=items, total=total, page=page, page_size=page_size)


@router.post("/sessions", response_model=SessionOut, status_code=201, responses=WRITE_ERRORS)
async def create_session(
    payload: CreateSessionRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    p = get_principal(request)
    owner_id = await resolve_chat_owner_id(session, p)
    factory_id = payload.factory_id.strip() if payload.factory_id else None
    if factory_id:
        enforce_factory_access(p, factory_id, "read")
    context = {"factory_id": factory_id} if factory_id else {}
    s = ChatSession(title=payload.title, context=context, user_id=owner_id)
    session.add(s)
    await session.commit()
    await session.refresh(s)
    return SessionOut(session_id=s.session_id, title=s.title, pinned=bool(s.pinned), context=s.context)


@router.patch("/sessions/{session_id}", response_model=SessionOut, responses={404: {"description": "Session not found"}, **WRITE_ERRORS})
async def update_session(
    session_id: UUID,
    payload: UpdateSessionRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    p = get_principal(request)
    s = await require_owned_session(session, session_id, p)
    if payload.title is not None:
        title = payload.title.strip()
        s.title = title or None
    if payload.pinned is not None:
        s.pinned = payload.pinned
        s.pinned_at = datetime.now(timezone.utc) if payload.pinned else None
    await session.commit()
    await session.refresh(s)
    return SessionOut(session_id=s.session_id, title=s.title, pinned=bool(s.pinned), context=s.context)


@router.delete("/sessions/{session_id}", status_code=204, responses={404: {"description": "Session not found"}, **WRITE_ERRORS})
async def delete_session(
    session_id: UUID,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    p = get_principal(request)
    s = await require_owned_session(session, session_id, p)
    await delete_session_attachment_files(session, session_id)
    await session.delete(s)
    await session.commit()


@router.post("/{session_id}/ask", response_model=AskResponse, responses={**READ_ERRORS, **WRITE_ERRORS})
async def ask(
    session_id: UUID,
    request: Request,
):
    from spark.core.database import AsyncSessionLocal
    from spark.services.chat_orchestrator import chat_orchestrator

    content_type = request.headers.get("content-type", "")
    if content_type.startswith("multipart/form-data"):
        async with AsyncSessionLocal() as session:
            return await _ask_multipart(session_id, request, session)

    try:
        body = await request.json()
    except Exception as exc:
        raise HTTPException(422, "invalid JSON request body") from exc
    try:
        req = AskRequest.model_validate(body)
    except ValidationError as exc:
        raise HTTPException(422, str(exc.errors()[0]["msg"])) from exc

    p = get_principal(request)

    if req.stream:
        from spark.services.streams.chat_stream_service import chat_stream_service

        return StreamingResponse(
            chat_stream_service.stream_ask(
                session_id=session_id,
                req=req,
                principal=p,
                request=request,
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    cached = await get_recent_ask(session_id, req.question)
    if cached is not None:
        return cached

    async with AsyncSessionLocal() as session:
        s = await require_owned_session(session, session_id, p)

        merged = chat_orchestrator._merge_filter(s.context, req.filter)
        from spark.core.qdrant_strategy import validate_factory_id_for_retrieval

        try:
            validate_factory_id_for_retrieval(merged.factory_id)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

        await enforce_rag_filter_access(session, p, merged)
        await enforce_or_bind_session_factory(session, s, p, merged.factory_id)
        response = await chat_orchestrator.ask(s, req, session, principal=p)
        await remember_ask(session_id, req.question, response)
        return response


async def _ask_multipart(
    session_id: UUID,
    request: Request,
    session: AsyncSession,
) -> AskResponse:

    p = get_principal(request)
    s = await require_owned_session(session, session_id, p)
    form = await request.form()
    try:
        return await _process_multipart(session_id, s, form, p, session)
    finally:
        await form.close()


async def _process_multipart(
    session_id: UUID,
    s,
    form,
    p,
    session: AsyncSession,
) -> AskResponse:
    from spark.services.chat_attachment_service import build_attachment_context
    from spark.services.chat_orchestrator import chat_orchestrator

    question = form.get("question")
    if not isinstance(question, str) or len(question.strip()) < 2:
        raise HTTPException(422, "question is required (min 2 characters)")

    filter_json = form.get("filter_json")
    filter_obj: RAGFilterModel | None = None
    if isinstance(filter_json, str) and filter_json.strip():
        try:
            filter_obj = RAGFilterModel.model_validate_json(filter_json)
        except ValidationError as exc:
            raise HTTPException(422, f"invalid filter_json: {exc.errors()[0]['msg']}") from exc

    top_k_raw = form.get("top_k")
    top_k = 6
    if isinstance(top_k_raw, str) and top_k_raw.strip():
        try:
            top_k = int(top_k_raw)
        except ValueError as exc:
            raise HTTPException(422, "invalid top_k") from exc
    if top_k < 1 or top_k > 20:
        raise HTTPException(422, "top_k must be between 1 and 20")

    files = [item for item in form.getlist("files") if hasattr(item, "read")]
    validate_attachment_uploads(files)

    req = AskRequest(question=question.strip(), filter=filter_obj, top_k=top_k)
    merged = chat_orchestrator._merge_filter(s.context, req.filter)
    factory_id = _resolve_factory_id(merged, s.context)
    from spark.core.qdrant_strategy import validate_factory_id_for_retrieval

    try:
        validate_factory_id_for_retrieval(factory_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    await enforce_rag_filter_access(session, p, merged)
    await enforce_or_bind_session_factory(session, s, p, factory_id)

    uploads: list[tuple[bytes, str, str]] = []
    for upload in files:
        uploads.append(await read_upload_bytes(upload))

    user_msg = ChatMessage(
        session_id=s.session_id,
        role="user",
        content=req.question,
        sources=None,
    )
    session.add(user_msg)
    await session.flush()

    saved_uris: list[str] = []
    try:
        prepared, saved_uris = await prepare_attachments(
            factory_id=factory_id,
            session_id=s.session_id,
            message_id=user_msg.message_id,
            uploads=uploads,
        )
        for att in prepared:
            session.add(
                ChatMessageAttachment(
                    message_id=user_msg.message_id,
                    session_id=s.session_id,
                    storage_uri=att.storage_uri,
                    original_filename=att.filename,
                    mime_type=att.mime_type,
                    file_size_bytes=att.file_size_bytes,
                    extracted_text=att.extracted_text,
                    extract_status="ok",
                    sort_order=att.sort_order,
                )
            )
        attachment_context = build_attachment_context(prepared)
        return await chat_orchestrator.ask(
            s,
            req,
            session,
            principal=p,
            attachment_context=attachment_context,
            existing_user_message=user_msg,
        )
    except AttachmentExtractError as exc:
        await session.rollback()
        await cleanup_storage_uris(saved_uris)
        raise HTTPException(422, str(exc)) from exc
    except HTTPException:
        await session.rollback()
        await cleanup_storage_uris(saved_uris)
        raise
    except Exception:
        await session.rollback()
        await cleanup_storage_uris(saved_uris)
        raise


@router.get("/{session_id}/messages", response_model=PaginatedResponse[ChatMessageOut], responses=READ_ERRORS)
async def list_messages(
    session_id: UUID,
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    factory_id: str | None = Query(None, min_length=1, max_length=64),
    session: AsyncSession = Depends(get_session),
):
    p = get_principal(request)
    chat_session = await require_owned_session(session, session_id, p)
    normalized_factory_id = factory_id.strip() if factory_id else None
    if normalized_factory_id:
        enforce_factory_access(p, normalized_factory_id, "read")
        scoped_factory_id = await enforce_or_bind_session_factory(
            session,
            chat_session,
            p,
            normalized_factory_id,
        )
        if scoped_factory_id and scoped_factory_id != normalized_factory_id:
            raise HTTPException(404, "session not found")
        await session.commit()
    base = select(ChatMessage).where(ChatMessage.session_id == session_id)
    count_stmt = select(func.count()).select_from(base.subquery())
    total = int((await session.execute(count_stmt)).scalar_one())
    offset = (page - 1) * page_size
    rows = (
        await session.execute(
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .options(selectinload(ChatMessage.attachments))
            .order_by(ChatMessage.created_at)
            .offset(offset)
            .limit(page_size)
        )
    ).scalars().all()
    return PaginatedResponse(
        items=[_message_out(session_id, m) for m in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


class RetrievalSnapshotOut(BaseModel):
    message_id: UUID
    session_id: UUID
    retrieval_snapshot: dict


class SessionSnapshotsOut(BaseModel):
    session_id: UUID
    snapshots: list[RetrievalSnapshotOut]


@router.get(
    "/{session_id}/snapshots",
    response_model=SessionSnapshotsOut,
    responses=READ_ERRORS,
)
async def list_session_retrieval_snapshots(
    session_id: UUID,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    """Admin/session replay — all retrieval audit snapshots for a chat session."""
    p = get_principal(request)
    if not p.is_admin:
        await require_owned_session(session, session_id, p)
    rows = (
        await session.execute(
            select(ChatMessage)
            .where(
                ChatMessage.session_id == session_id,
                ChatMessage.role == "assistant",
                ChatMessage.retrieval_snapshot.isnot(None),
            )
            .order_by(ChatMessage.created_at.asc())
        )
    ).scalars().all()
    return SessionSnapshotsOut(
        session_id=session_id,
        snapshots=[
            RetrievalSnapshotOut(
                message_id=row.message_id,
                session_id=session_id,
                retrieval_snapshot=row.retrieval_snapshot or {},
            )
            for row in rows
        ],
    )


@router.get(
    "/{session_id}/messages/{message_id}/retrieval-snapshot",
    response_model=RetrievalSnapshotOut,
    responses=READ_ERRORS,
)
async def get_retrieval_snapshot(
    session_id: UUID,
    message_id: UUID,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    """Read-only retrieval audit replay for compliance reviewers."""
    p = get_principal(request)
    if not p.is_admin:
        await require_owned_session(session, session_id, p)
    msg = await session.get(ChatMessage, message_id)
    if msg is None or msg.session_id != session_id:
        raise HTTPException(404, "message not found")
    if msg.role != "assistant":
        raise HTTPException(400, "retrieval snapshot available only on assistant messages")
    if not msg.retrieval_snapshot:
        raise HTTPException(404, "no retrieval snapshot for this message")
    return RetrievalSnapshotOut(
        message_id=message_id,
        session_id=session_id,
        retrieval_snapshot=msg.retrieval_snapshot,
    )


@router.get(
    "/{session_id}/messages/{message_id}/attachments/{sort_order}",
    responses=READ_ERRORS,
)
async def stream_chat_attachment(
    session_id: UUID,
    message_id: UUID,
    sort_order: int,
    request: Request,
):
    p = get_principal(request)
    async with AsyncSessionLocal() as session:
        await require_owned_session(session, session_id, p)

        attachment = (
            await session.execute(
                select(ChatMessageAttachment).where(
                    ChatMessageAttachment.session_id == session_id,
                    ChatMessageAttachment.message_id == message_id,
                    ChatMessageAttachment.sort_order == sort_order,
                )
            )
        ).scalar_one_or_none()
        if attachment is None:
            raise HTTPException(404, "attachment not found")

        storage_uri = attachment.storage_uri
        mime_type = attachment.mime_type
        filename = attachment.original_filename

    storage = get_storage()
    if not await storage.exists(storage_uri):
        raise HTTPException(404, "attachment file not found")

    return StreamingResponse(
        open_storage_object_async(storage_uri),
        media_type=mime_type,
        headers={
            "Content-Disposition": f'inline; filename="{filename}"',
        },
    )


@router.post(
    "/messages/{message_id}/verify",
    responses=WRITE_ERRORS,
)
async def verify_chat_message(
    message_id: UUID,
    request: Request,
    factory_id: str = Query(..., min_length=1),
    session: AsyncSession = Depends(get_session),
):
    from spark.services.qa_cache_service import qa_cache_service

    p = get_principal(request)
    if not p.is_admin:
        raise HTTPException(403, "admin required to verify answers")
    msg = await session.get(ChatMessage, message_id)
    if msg is None:
        raise HTTPException(404, "message not found")
    if msg.role != "assistant":
        raise HTTPException(400, "only assistant messages can be verified")
    await require_owned_session(session, msg.session_id, p)
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
    if prior_user is None:
        raise HTTPException(400, "no user question found for this answer")
    try:
        entry = await qa_cache_service.verify_message(
            session,
            message=msg,
            factory_id=factory_id,
            question_text=prior_user.content,
            principal=p,
        )
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    await session.commit()
    return {"cache_id": str(entry.cache_id), "verified": True}
