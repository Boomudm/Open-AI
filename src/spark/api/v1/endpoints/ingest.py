from __future__ import annotations

import hashlib
import io
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from spark.api.openapi_responses import WRITE_ERRORS
from spark.api.upload_utils import read_upload_bounded
from spark.services.document_revision import revision_sort_key_from_label
from spark.core.config import settings
from spark.core.database import get_session
from spark.core.logging import get_logger
from spark.core.security import enforce_write_factory, get_principal
from spark.db.models.docs import Document
from spark.db.models.ingestion import IngestionJob
from spark.ingestion.config_loader import list_document_types, load_config
from spark.ingestion.config_resolver import resolve_ingest_config
from spark.ingestion.document_type_resolver import resolve_document_type
from spark.ingestion.idempotency import find_existing_job, ingest_idempotency_key
from spark.schemas.documents import IngestFileResponse
from spark.services.document_mime import validate_upload_mime
from spark.services.ingest_dedup import find_document_by_upload_hash, mark_document_reingest_pending
from spark.services.ingest_rate_limit import check_reingest_rate_limit, check_single_file_rate_limit
from spark.services.ingest_scope import (
    parse_visible_position_ids,
    resolve_ingest_factory_id,
    set_document_job_positions,
    validate_active_position_ids,
)
from spark.storage import get_storage

log = get_logger(__name__)

router = APIRouter(prefix="/ingest", tags=["Ingestion"])


def _hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _created_by_from_principal_user_id(user_id: str) -> uuid.UUID | None:
    try:
        created_by = uuid.UUID(user_id)
    except ValueError:
        return None
    if created_by.int == 0:
        return None
    return created_by


@router.get("/document-types")
async def get_document_types(request: Request) -> list[str]:
    get_principal(request)
    return list_document_types()


@router.post("/file", response_model=IngestFileResponse, status_code=202, responses=WRITE_ERRORS)
async def ingest_file(
    request: Request,
    file: UploadFile = File(..., description="PDF, Excel, Word, or other supported document"),
    document_type: str | None = Form(None, examples=["machine_manual"]),
    machine_id: str | None = Form(None, examples=["MC-001"]),
    factory_id: str | None = Form(None, examples=["F-01"]),
    revision: str | None = Form(None, examples=["v1"]),
    drawing_no: str | None = Form(None, examples=["EE-13"]),
    title: str | None = Form(None, examples=["Servo Motor Manual"]),
    visible_position_ids: str | None = Form(
        None,
        description='JSON array of job position UUIDs, e.g. ["uuid1","uuid2"]',
    ),
    session: AsyncSession = Depends(get_session),
):
    p = get_principal(request)
    resolved_factory_id = await resolve_ingest_factory_id(
        session,
        factory_id=factory_id,
        machine_id=machine_id,
    )
    enforce_write_factory(p, resolved_factory_id)
    await check_single_file_rate_limit(resolved_factory_id)

    machine_key = (machine_id or "").strip() or None
    position_ids = parse_visible_position_ids(visible_position_ids)
    await validate_active_position_ids(session, position_ids)

    if not file.filename:
        raise HTTPException(400, "missing filename")

    raw_bytes = await read_upload_bounded(file, settings.max_upload_bytes)

    resolved_type = resolve_document_type(file.filename, document_type, content=raw_bytes)
    if not resolved_type:
        raise HTTPException(
            400, f"cannot resolve document_type for {file.filename}; pass document_type explicitly"
        )

    try:
        config = load_config(resolved_type)
    except FileNotFoundError as exc:
        raise HTTPException(400, "unknown document type configuration") from exc
    if "machine_id" in (config.get("required_metadata") or []) and not machine_id:
        raise HTTPException(400, f"document_type {resolved_type!r} requires machine_id — select a machine")

    try:
        mime = validate_upload_mime(file.filename, raw_bytes)
    except ValueError as exc:
        raise HTTPException(415, str(exc)) from exc

    file_hash = _hash_bytes(raw_bytes)
    file_size = len(raw_bytes)
    storage = get_storage()

    existing = await find_document_by_upload_hash(
        session,
        factory_id=resolved_factory_id,
        file_hash=file_hash,
        machine_id=machine_key,
    )
    created_by = _created_by_from_principal_user_id(p.user_id)

    if existing:
        await check_reingest_rate_limit(resolved_factory_id)
        doc = await mark_document_reingest_pending(
            session,
            existing,
            factory_id=resolved_factory_id,
            machine_id=machine_key,
            document_type=resolved_type,
            document_category=config.get("document_category"),
        )
        if title:
            doc.title = title
        if revision:
            doc.revision = revision
            doc.revision_sort_key = revision_sort_key_from_label(revision)
        if not doc.storage_uri or not await storage.exists(doc.storage_uri):
            stream = io.BytesIO(raw_bytes)
            doc.storage_uri = await storage.save_document(
                doc.doc_id,
                file.filename,
                stream,
                factory_id=resolved_factory_id,
                document_type=resolved_type,
                machine_id=machine_key,
                content_type=mime,
            )
            doc.file_size_bytes = file_size
        await set_document_job_positions(session, doc.doc_id, position_ids)
    else:
        doc_id = uuid.uuid4()
        stream = io.BytesIO(raw_bytes)
        storage_uri = await storage.save_document(
            doc_id,
            file.filename,
            stream,
            factory_id=resolved_factory_id,
            document_type=resolved_type,
            machine_id=machine_key,
            content_type=mime,
        )
        doc = Document(
            doc_id=doc_id,
            factory_id=resolved_factory_id,
            machine_id=machine_key,
            document_category=config.get("document_category"),
            document_type=resolved_type,
            title=title or file.filename,
            revision=revision,
            revision_sort_key=revision_sort_key_from_label(revision),
            source_file=file.filename,
            original_filename=file.filename,
            mime_type=mime,
            storage_uri=storage_uri,
            file_hash_sha256=file_hash,
            file_size_bytes=file_size,
            ingest_status="pending",
            created_by=created_by,
        )
        session.add(doc)
        await session.flush()
        await set_document_job_positions(session, doc.doc_id, position_ids)

    if not doc.storage_uri or not await storage.exists(doc.storage_uri):
        raise HTTPException(500, "stored file is not available for ingestion")

    factory_cfg: dict = {}
    if resolved_factory_id:
        from spark.services.factory_config_service import factory_config_service

        factory_cfg = await factory_config_service.resolve(session, resolved_factory_id)
    resolved_cfg = resolve_ingest_config(resolved_type, factory_cfg)
    idempotency_key = ingest_idempotency_key(
        doc.doc_id,
        file_hash,
        resolved_cfg.config_hash(),
    )
    existing_job = await find_existing_job(session, idempotency_key)
    if existing_job is not None:
        return IngestFileResponse(
            job_id=existing_job.job_id,
            doc_id=doc.doc_id,
            status=existing_job.status,
            celery_task_id=existing_job.celery_task_id,
        )

    job = IngestionJob(
        job_id=uuid.uuid4(),
        doc_id=doc.doc_id,
        document_type=resolved_type,
        original_filename=file.filename,
        file_size_bytes=file_size,
        factory_id=resolved_factory_id,
        machine_id=machine_key,
        status="queued",
        idempotency_key=idempotency_key,
    )
    session.add(job)
    await session.commit()

    context = {
        "factory_id": resolved_factory_id,
        "machine_id": machine_key,
        "document_type": resolved_type,
        "document_category": config.get("document_category"),
        "language": "th",
        "revision": revision,
        "revision_sort_key": revision_sort_key_from_label(revision),
        "drawing_no": (drawing_no or "").strip() or None,
        "title": title or file.filename,
        "source_file": file.filename,
        "file_hash_sha256": file_hash,
        "config_hash": resolved_cfg.config_hash(),
    }

    from spark.workers.tasks import ingest_document_task

    async_result = ingest_document_task.delay(
        doc_id=str(doc.doc_id),
        storage_uri=doc.storage_uri,
        document_type=resolved_type,
        document_context=context,
        job_id=str(job.job_id),
    )

    job.celery_task_id = async_result.id
    await session.commit()

    return IngestFileResponse(
        job_id=job.job_id,
        doc_id=doc.doc_id,
        status="queued",
        celery_task_id=async_result.id,
    )


@router.post(
    "/documents/{doc_id}/reingest",
    response_model=IngestFileResponse,
    status_code=202,
    responses=WRITE_ERRORS,
    summary="Trigger reingest for an existing document",
)
async def reingest_document(
    doc_id: uuid.UUID,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> IngestFileResponse:
    """Re-queue ingestion for a document that has already been stored. Useful after
    config changes or to recover from a failed/partial ingest without re-uploading."""
    p = get_principal(request)
    doc = await session.get(Document, doc_id)
    if doc is None:
        raise HTTPException(404, "document not found")
    enforce_write_factory(p, doc.factory_id)
    if not doc.storage_uri:
        raise HTTPException(409, "document has no stored file — cannot reingest")

    storage = get_storage()
    if not await storage.exists(doc.storage_uri):
        raise HTTPException(409, "document file is no longer in storage")

    await check_reingest_rate_limit(doc.factory_id)

    # Check for an already-active job to avoid double-dispatch
    active = await session.scalar(
        select(IngestionJob)
        .where(
            IngestionJob.doc_id == doc_id,
            IngestionJob.status.in_(("queued", "running", "started")),
        )
        .limit(1)
    )
    if active:
        raise HTTPException(409, f"document already has an active ingest job ({active.job_id})")

    doc.ingest_status = "pending"
    job = IngestionJob(
        job_id=uuid.uuid4(),
        doc_id=doc.doc_id,
        document_type=doc.document_type,
        original_filename=doc.source_file,
        file_size_bytes=doc.file_size_bytes,
        factory_id=doc.factory_id,
        machine_id=doc.machine_id,
        status="queued",
    )
    session.add(job)
    await session.commit()

    context = {
        "factory_id": doc.factory_id,
        "machine_id": doc.machine_id,
        "document_type": doc.document_type,
        "document_category": doc.document_category,
        "language": doc.language,
        "revision": doc.revision,
        "revision_sort_key": doc.revision_sort_key,
        "title": doc.title,
        "source_file": doc.source_file,
        "file_hash_sha256": doc.file_hash_sha256,
    }

    from spark.workers.tasks import ingest_document_task

    async_result = ingest_document_task.delay(
        doc_id=str(doc.doc_id),
        storage_uri=doc.storage_uri,
        document_type=doc.document_type,
        document_context=context,
        job_id=str(job.job_id),
    )
    job.celery_task_id = async_result.id
    await session.commit()

    return IngestFileResponse(
        job_id=job.job_id,
        doc_id=doc.doc_id,
        status="queued",
        celery_task_id=async_result.id,
    )
