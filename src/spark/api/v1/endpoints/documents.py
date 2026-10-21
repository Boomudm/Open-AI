from __future__ import annotations

from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from spark.api.openapi_responses import READ_ERRORS, WRITE_ERRORS
from spark.core.database import get_session
from spark.core.logging import get_logger
from spark.core.qdrant_strategy import collection_for_document
from spark.core.security import enforce_factory_access, enforce_write_factory, get_principal
from spark.db.models.docs import Document
from spark.db.models.ingestion import IngestionJob
from spark.ingestion.index.qdrant_writer import QdrantRouter
from spark.schemas.documents import DocumentOut, DocumentVisibilityUpdate
from spark.schemas.pagination import PaginatedResponse
from spark.services.document_access_service import (
    allowed_doc_ids_for_principal,
    can_access_document,
    document_list_factory_filter,
    log_document_access,
    restricted_position_ids_for_docs,
)
from spark.services.document_mime import is_allowed_mime, resolve_document_mime
from spark.services.ingest_scope import set_document_job_positions, validate_active_position_ids
from spark.storage import get_storage
from spark.storage.resolve import open_storage_object_async, storage_object_exists_async

log = get_logger(__name__)

router = APIRouter(prefix="/documents", tags=["Documents"])


def _client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return None


def _display_filename(doc: Document) -> str:
    return doc.original_filename or doc.source_file or str(doc.doc_id)


def _document_out(doc: Document, positions: list[UUID]) -> DocumentOut:
    return DocumentOut.model_validate(doc, from_attributes=True).model_copy(
        update={"visible_position_ids": positions}
    )


@router.get("", response_model=PaginatedResponse[DocumentOut], responses=READ_ERRORS)
async def list_documents(
    request: Request,
    factory_id: str | None = Query(None),
    machine_id: str | None = None,
    document_type: str | None = None,
    document_category: str | None = None,
    status: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    limit: int | None = Query(None, ge=1, le=200, deprecated=True),
    offset: int | None = Query(None, ge=0, deprecated=True),
    session: AsyncSession = Depends(get_session),
):
    p = get_principal(request)
    enforce_factory_access(p, factory_id, "read")

    if limit is not None:
        page_size = limit
    if offset is not None:
        page = offset // page_size + 1 if page_size else 1

    allowed_ids = await allowed_doc_ids_for_principal(session, p)
    if allowed_ids is not None and not allowed_ids:
        return PaginatedResponse(items=[], total=0, page=page, page_size=page_size)

    stmt = select(Document)
    factory_clause = document_list_factory_filter(p)
    if factory_clause is not None:
        stmt = stmt.where(factory_clause)
    if factory_id:
        stmt = stmt.where(Document.factory_id == factory_id)
    if machine_id:
        stmt = stmt.where(Document.machine_id == machine_id)
    if document_type:
        stmt = stmt.where(Document.document_type == document_type)
    if document_category:
        stmt = stmt.where(Document.document_category == document_category)
    if status:
        stmt = stmt.where(Document.ingest_status == status)
    if allowed_ids is not None:
        stmt = stmt.where(Document.doc_id.in_(allowed_ids))

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = int((await session.execute(count_stmt)).scalar_one())

    page_offset = (page - 1) * page_size
    rows = (
        await session.execute(
            stmt.order_by(Document.created_at.desc()).limit(page_size).offset(page_offset)
        )
    ).scalars().all()
    position_map = await restricted_position_ids_for_docs(session, [row.doc_id for row in rows])
    items = [
        _document_out(row, position_map.get(row.doc_id, []))
        for row in rows
    ]
    return PaginatedResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/{doc_id}/file", responses=READ_ERRORS)
async def get_document_file(
    doc_id: UUID,
    request: Request,
    disposition: str = Query("inline", pattern="^(inline|download)$"),
    session: AsyncSession = Depends(get_session),
):
    p = get_principal(request)
    doc = await session.get(Document, doc_id)
    if not doc:
        raise HTTPException(404, "document not found")
    if not await can_access_document(session, p, doc):
        raise HTTPException(403, "no access to document")
    if not doc.storage_uri:
        raise HTTPException(404, "file not available")

    if not await storage_object_exists_async(doc.storage_uri):
        raise HTTPException(404, "file not found on storage")

    mime = resolve_document_mime(
        mime_type=doc.mime_type,
        original_filename=doc.original_filename,
        source_file=doc.source_file,
    )
    if not is_allowed_mime(mime):
        raise HTTPException(415, "file type not allowed")

    filename = _display_filename(doc)
    action = "download" if disposition == "download" else "view"
    await log_document_access(
        session,
        doc_id=doc.doc_id,
        user_id=p.user_id,
        action=action,
        ip=_client_ip(request),
    )
    await session.commit()

    safe_ascii = filename.encode("ascii", "ignore").decode().strip() or "document"
    encoded = quote(filename)
    disp = "attachment" if disposition == "download" else "inline"
    content_disp = f"{disp}; filename=\"{safe_ascii}\"; filename*=UTF-8''{encoded}"

    headers: dict[str, str] = {
        "Content-Disposition": content_disp,
        "Cache-Control": "private, no-cache",
    }
    if doc.file_hash_sha256:
        headers["ETag"] = f'"{doc.file_hash_sha256}"'
        inm = request.headers.get("if-none-match", "").strip().strip('"')
        if inm and inm == doc.file_hash_sha256:
            from fastapi.responses import Response

            return Response(status_code=304, headers=headers)

    return StreamingResponse(
        open_storage_object_async(doc.storage_uri),
        media_type=mime,
        headers=headers,
    )


@router.get("/{doc_id}", response_model=DocumentOut, responses=READ_ERRORS)
async def get_document(
    doc_id: UUID,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    p = get_principal(request)
    doc = await session.get(Document, doc_id)
    if not doc:
        raise HTTPException(404, "document not found")
    if not await can_access_document(session, p, doc):
        raise HTTPException(403, "no access to document")
    position_map = await restricted_position_ids_for_docs(session, [doc.doc_id])
    return _document_out(doc, position_map.get(doc.doc_id, []))


@router.patch("/{doc_id}/visibility", response_model=DocumentOut, responses=WRITE_ERRORS)
async def update_document_visibility(
    doc_id: UUID,
    payload: DocumentVisibilityUpdate,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    p = get_principal(request)
    doc = await session.get(Document, doc_id)
    if not doc:
        raise HTTPException(404, "document not found")
    enforce_write_factory(p, doc.factory_id)
    await validate_active_position_ids(session, payload.visible_position_ids)
    await set_document_job_positions(session, doc.doc_id, payload.visible_position_ids)
    await session.commit()
    await session.refresh(doc)
    return _document_out(doc, payload.visible_position_ids)


@router.delete("/{doc_id}", status_code=204, responses=READ_ERRORS)
async def delete_document(
    doc_id: UUID,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    p = get_principal(request)
    doc = await session.get(Document, doc_id)
    if not doc:
        raise HTTPException(404, "document not found")
    enforce_write_factory(p, doc.factory_id)

    router_q = QdrantRouter()
    coll = collection_for_document(doc.document_type, doc.factory_id, doc.document_category)
    await router_q.delete_by_doc(doc_id, collection=coll)

    if doc.storage_uri:
        try:
            await get_storage().delete(doc.storage_uri)
        except Exception as exc:
            log.warning("document_storage_delete_failed", doc_id=str(doc_id), error=str(exc)[:200])

    # Mark jobs 'deleted' before removing the document — ingestion_jobs.doc_id
    # is ON DELETE SET NULL (not CASCADE), so these rows survive with doc_id
    # cleared. Without this, the row would go straight from its terminal
    # status (queued/failed/completed) to orphaned-but-still-counted, giving
    # no way for the Ingest Jobs chart to tell "deleted" apart from "still
    # queued" — the whole point of this status.
    await session.execute(
        update(IngestionJob).where(IngestionJob.doc_id == doc_id).values(status="deleted")
    )
    await session.delete(doc)
    await session.commit()
    log.info("document_deleted", doc_id=str(doc_id))
