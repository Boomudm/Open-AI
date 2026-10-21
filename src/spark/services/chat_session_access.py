"""Per-user ownership checks for chat sessions."""

from __future__ import annotations

import uuid

from fastapi import HTTPException
from sqlalchemy import ColumnElement
from sqlalchemy.ext.asyncio import AsyncSession

from spark.core.security import Principal, enforce_factory_access
from spark.db.models.chat import ChatSession
from spark.db.models.org import User


def principal_user_id(p: Principal) -> uuid.UUID:
    try:
        return uuid.UUID(p.user_id)
    except ValueError as exc:
        raise HTTPException(401, "invalid user identity") from exc


async def resolve_chat_owner_id(db: AsyncSession, p: Principal) -> uuid.UUID | None:
    """Return JWT user id when the user row exists; otherwise None (legacy dev principal)."""
    uid = principal_user_id(p)
    if await db.get(User, uid) is not None:
        return uid
    return None


def chat_owner_clause(owner_id: uuid.UUID | None) -> ColumnElement[bool]:
    if owner_id is None:
        return ChatSession.user_id.is_(None)
    return ChatSession.user_id == owner_id


def chat_session_factory_clause(factory_id: str) -> ColumnElement[bool]:
    return ChatSession.context.op("->>")("factory_id") == factory_id


def chat_session_unbound_factory_clause() -> ColumnElement[bool]:
    """Sessions created before factory scoping (no factory_id in context JSON)."""
    from sqlalchemy import func, or_

    bound = func.nullif(func.trim(ChatSession.context.op("->>")("factory_id")), "")
    return or_(ChatSession.context.is_(None), bound.is_(None))


def session_factory_id(row: ChatSession) -> str | None:
    context = row.context if isinstance(row.context, dict) else {}
    raw = context.get("factory_id")
    factory_id = str(raw).strip() if raw is not None else ""
    return factory_id or None


async def enforce_or_bind_session_factory(
    db: AsyncSession,
    row: ChatSession,
    p: Principal,
    factory_id: str | None,
) -> str | None:
    normalized = str(factory_id or "").strip()
    if not normalized:
        return session_factory_id(row)

    enforce_factory_access(p, normalized, "read")
    existing = session_factory_id(row)
    if existing and existing != normalized:
        raise HTTPException(409, "chat session belongs to another factory")
    if not existing:
        context = dict(row.context or {})
        context["factory_id"] = normalized
        row.context = context
        await db.flush()
    return normalized


async def require_owned_session(
    db: AsyncSession,
    session_id: uuid.UUID,
    p: Principal,
) -> ChatSession:
    row = await db.get(ChatSession, session_id)
    owner_id = await resolve_chat_owner_id(db, p)
    if row is None:
        raise HTTPException(404, "session not found")
    if owner_id is None:
        if row.user_id is not None:
            raise HTTPException(404, "session not found")
    elif row.user_id != owner_id:
        raise HTTPException(404, "session not found")
    return row
