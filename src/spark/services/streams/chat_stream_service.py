"""Chat SSE without holding a request-scoped DB session (app-layer Phase 3)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from uuid import UUID

from fastapi import HTTPException, Request, status

from spark.api.platform.errors import _code_for_status
from spark.core.database import StreamSessionLocal
from spark.core.qdrant_strategy import validate_factory_id_for_retrieval
from spark.core.security import Principal, enforce_rag_filter_access
from spark.db.models.chat import ChatSession
from spark.schemas.rag import AskRequest
from spark.services.chat_ask_dedupe import try_begin_stream_ask
from spark.services.chat_orchestrator import chat_orchestrator
from spark.services.chat_session_access import enforce_or_bind_session_factory, require_owned_session
from spark.services.chat_stream import sse_error
from spark.services.streams.connection_governor import connection_governor, ensure_sse_connection
from spark.services.streams.disconnect import track_disconnect, with_sse_keepalive


class ChatStreamService:
    async def stream_ask(
        self,
        *,
        session_id: UUID,
        req: AskRequest,
        principal: Principal,
        request: Request,
    ) -> AsyncIterator[str]:
        """Validate access with a short DB scope, then stream without pool checkout."""
        request.state.admission_plane = "sse"
        user_id = principal.user_id or "anonymous"
        ensure_sse_connection(user_id=user_id, channel="chat_ask")
        try:
            if not await try_begin_stream_ask(session_id, req.question):
                yield sse_error("duplicate_ask", "duplicate stream ask within dedupe window")
                return
            cancel_event = asyncio.Event()
            try:
                try:
                    async with asyncio.timeout(90):
                        async for frame in track_disconnect(
                            request,
                            with_sse_keepalive(
                                self._stream_ask(
                                    session_id=session_id,
                                    req=req,
                                    principal=principal,
                                    cancel_event=cancel_event,
                                )
                            ),
                            cancel_event=cancel_event,
                        ):
                            yield frame
                except TimeoutError:
                    cancel_event.set()
                    yield sse_error(
                        "stream_timeout",
                        "AI ใช้เวลาตอบนานเกิน 90 วินาที กรุณาลองใหม่อีกครั้ง",
                    )
            except HTTPException as exc:
                # Access/validation checks (require_owned_session,
                # enforce_or_bind_session_factory, ...) run inside this
                # generator, after the StreamingResponse has already
                # committed to a 200 + SSE body — an HTTPException raised
                # here can no longer change the HTTP status, so it must be
                # surfaced as an SSE error frame instead of propagating to
                # the generic unhandled-exception 500 handler.
                detail = exc.detail
                message = detail if isinstance(detail, str) else str(detail)
                yield sse_error(_code_for_status(exc.status_code, detail), message)
        finally:
            connection_governor.release(user_id=user_id, channel="chat_ask")

    async def _stream_ask(
        self,
        *,
        session_id: UUID,
        req: AskRequest,
        principal: Principal,
        cancel_event: asyncio.Event,
    ) -> AsyncIterator[str]:
        async with StreamSessionLocal() as db:
            session_row = await require_owned_session(db, session_id, principal)
            merged = chat_orchestrator._merge_filter(session_row.context, req.filter)
            try:
                validate_factory_id_for_retrieval(merged.factory_id)
            except ValueError as exc:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
            await enforce_rag_filter_access(db, principal, merged)
            await enforce_or_bind_session_factory(db, session_row, principal, merged.factory_id)
            session_snapshot = ChatSession(
                session_id=session_row.session_id,
                user_id=session_row.user_id,
                title=session_row.title,
                context=dict(session_row.context or {}),
            )
            await db.commit()

        async for frame in chat_orchestrator.ask_stream(
            session_snapshot,
            req,
            principal=principal,
            cancel_event=cancel_event,
        ):
            yield frame


chat_stream_service = ChatStreamService()
