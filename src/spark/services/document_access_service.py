from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from spark.core.security import Principal, accessible_factory_ids, can_access_factory

if TYPE_CHECKING:
    from spark.db.models.docs import Document


def _user_position_uuids(principal: Principal) -> set[uuid.UUID]:
    out: set[uuid.UUID] = set()
    for raw in principal.job_position_ids:
        try:
            out.add(uuid.UUID(str(raw)))
        except ValueError:
            continue
    return out


def passes_job_position_acl(
    principal: Principal,
    restricted_position_ids: set[uuid.UUID] | None,
) -> bool:
    if restricted_position_ids is None:
        return True
    if not restricted_position_ids:
        return False
    user_positions = _user_position_uuids(principal)
    return bool(user_positions & restricted_position_ids)


def _passes_factory_acl(principal: Principal, doc: Document) -> bool:
    if doc.factory_id is None:
        return bool(principal.factory_access)
    return can_access_factory(principal, doc.factory_id, "read")


async def restricted_position_ids_for_doc(
    session: AsyncSession,
    doc_id: uuid.UUID,
) -> set[uuid.UUID] | None:
    """Return active restricted position IDs, or None when the document is unrestricted."""
    mapping = await restricted_position_ids_for_docs(session, [doc_id])
    positions = mapping.get(doc_id)
    if positions is None:
        return None
    return set(positions)


async def restricted_position_ids_for_docs(
    session: AsyncSession,
    doc_ids: list[uuid.UUID],
) -> dict[uuid.UUID, list[uuid.UUID]]:
    """Batch load position ACL per doc. Docs with no rows are omitted (unrestricted)."""
    from spark.db.models.job_positions import DocumentJobPosition, JobPosition

    if not doc_ids:
        return {}

    rows = (
        await session.execute(
            select(DocumentJobPosition.doc_id, DocumentJobPosition.position_id)
            .join(JobPosition, JobPosition.position_id == DocumentJobPosition.position_id)
            .where(
                DocumentJobPosition.doc_id.in_(doc_ids),
                JobPosition.is_active.is_(True),
            )
        )
    ).all()

    out: dict[uuid.UUID, list[uuid.UUID]] = {}
    for doc_id, position_id in rows:
        out.setdefault(doc_id, []).append(position_id)
    return out


async def can_access_document(
    session: AsyncSession,
    principal: Principal,
    doc: Document,
) -> bool:
    if principal.is_admin:
        return True
    if not _passes_factory_acl(principal, doc):
        return False
    restricted = await restricted_position_ids_for_doc(session, doc.doc_id)
    if restricted is None:
        return True
    return passes_job_position_acl(principal, restricted)


async def compute_allowed_doc_ids(
    session: AsyncSession,
    principal: Principal,
    *,
    factory_id: str | None = None,
) -> list[uuid.UUID] | None:
    """Compute allowed doc IDs (cache miss path)."""
    from sqlalchemy import text

    from spark.db.models.docs import Document
    from spark.db.models.job_positions import DocumentJobPosition, JobPosition
    from spark.services.acl.factory_doc_index import list_factory_doc_ids, rebuild_factory_doc_index

    if principal.is_admin:
        return None

    allowed_factories = accessible_factory_ids(principal)
    if factory_id:
        if allowed_factories is not None and factory_id not in allowed_factories:
            return []
        allowed_factories = [factory_id]
    elif allowed_factories is not None and len(allowed_factories) == 1:
        factory_id = allowed_factories[0]

    if not allowed_factories:
        return []

    try:
        await session.execute(text("SET LOCAL statement_timeout = 5000"))
    except Exception:
        pass

    factory_clause = or_(
        Document.factory_id.in_(allowed_factories),
        Document.factory_id.is_(None),
    )

    doc_id_scope = None
    if factory_id:
        doc_id_scope = await list_factory_doc_ids(factory_id)
        if doc_id_scope is None:
            await rebuild_factory_doc_index(session, factory_id)
            doc_id_scope = await list_factory_doc_ids(factory_id)

    unrestricted = ~exists(
        select(DocumentJobPosition.doc_id).where(DocumentJobPosition.doc_id == Document.doc_id)
    )

    user_positions = _user_position_uuids(principal)
    if not user_positions:
        stmt = select(Document.doc_id).where(factory_clause, unrestricted)
    else:
        position_match = exists(
            select(DocumentJobPosition.doc_id).where(
                DocumentJobPosition.doc_id == Document.doc_id,
                DocumentJobPosition.position_id.in_(user_positions),
                DocumentJobPosition.position_id.in_(
                    select(JobPosition.position_id).where(JobPosition.is_active.is_(True))
                ),
            )
        )
        stmt = select(Document.doc_id).where(
            factory_clause,
            or_(unrestricted, position_match),
        )

    if doc_id_scope is not None:
        if not doc_id_scope:
            return []
        stmt = stmt.where(Document.doc_id.in_(doc_id_scope))

    rows = (await session.execute(stmt)).scalars().all()
    return list(rows)


async def allowed_doc_ids_for_principal(
    session: AsyncSession,
    principal: Principal,
    *,
    factory_id: str | None = None,
) -> list[uuid.UUID] | None:
    """Return allowed doc IDs, or None when admin (no Qdrant doc_id filter)."""
    from spark.services.acl.document_acl_cache import allowed_doc_ids_for_principal_cached

    return await allowed_doc_ids_for_principal_cached(
        session,
        principal,
        factory_id=factory_id,
    )


def document_list_factory_filter(principal: Principal):
    """SQLAlchemy filter for list_documents (factory scope only; position filter applied in endpoint)."""
    from spark.db.models.docs import Document

    allowed = accessible_factory_ids(principal)
    if allowed is None:
        return None
    if not allowed:
        return Document.factory_id.in_([])
    return or_(
        Document.factory_id.in_(allowed),
        Document.factory_id.is_(None),
    )


async def document_ids_visible_to_principal(
    session: AsyncSession,
    principal: Principal,
    doc_ids: list[uuid.UUID],
) -> set[uuid.UUID]:
    """Filter doc IDs by factory + job-position ACL."""
    if principal.is_admin or not doc_ids:
        return set(doc_ids)

    allowed = await allowed_doc_ids_for_principal(session, principal)
    if allowed is None:
        return set(doc_ids)
    allowed_set = set(allowed)
    return {doc_id for doc_id in doc_ids if doc_id in allowed_set}


async def log_document_access(
    session: AsyncSession,
    *,
    doc_id: uuid.UUID,
    user_id: str | None,
    action: str,
    ip: str | None,
) -> None:
    from spark.db.models.docs import DocumentAccessLog
    from spark.db.models.org import User

    uid: uuid.UUID | None = None
    if user_id:
        try:
            parsed = uuid.UUID(user_id)
        except ValueError:
            parsed = None
        if parsed is not None and await session.get(User, parsed) is not None:
            uid = parsed

    session.add(
        DocumentAccessLog(
            doc_id=doc_id,
            user_id=uid,
            action=action,
            ip=ip,
        )
    )
