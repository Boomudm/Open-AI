from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from spark.api.openapi_responses import READ_ERRORS, WRITE_ERRORS
from spark.core.database import get_session
from spark.core.security import (
    accessible_factory_ids,
    can_write_factory,
    enforce_factory_access,
    get_principal,
)
from spark.schemas.machines import (
    AliasCreate,
    AliasOut,
    MachineCreate,
    MachineOut,
    MachinePatch,
)
from spark.schemas.pagination import PaginatedResponse
from spark.core.config import settings
from spark.services.image_mime import (
    guess_image_mime_from_name,
    is_allowed_image_mime,
)
from spark.services.machine_image_service import (
    MAX_MACHINE_IMAGE_BYTES,
    delete_machine_image as delete_machine_image_storage,
    save_machine_image,
)
from spark.services.master_data_service import MasterDataService
from spark.storage import get_storage
from spark.storage.resolve import open_storage_object_async
from spark.storage.uri import is_file_uri, is_s3_uri, parse_file_uri, parse_s3_uri

router = APIRouter(prefix="/machines", tags=["Machines"])
service = MasterDataService()


def _mime_from_storage_uri(storage_uri: str) -> str | None:
    if is_s3_uri(storage_uri):
        _, key = parse_s3_uri(storage_uri)
        return guess_image_mime_from_name(key)
    if is_file_uri(storage_uri):
        return guess_image_mime_from_name(parse_file_uri(storage_uri).name)
    return None


@router.get("", response_model=PaginatedResponse[MachineOut], responses=READ_ERRORS)
async def list_machines(
    request: Request,
    factory_id: str | None = None,
    machine_type: str | None = None,
    q: str | None = Query(None, max_length=200),
    include_inactive: bool = False,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
):
    p = get_principal(request)
    enforce_factory_access(p, factory_id, "read")
    if include_inactive:
        if factory_id and not can_write_factory(p, factory_id):
            raise HTTPException(403, "include_inactive requires factory write access")
        if not factory_id and "admin" not in p.roles and not any(
            can_write_factory(p, fid) for fid in (accessible_factory_ids(p) or [])
        ):
            raise HTTPException(403, "include_inactive requires factory write access")
    allowed = accessible_factory_ids(p)
    offset = (page - 1) * page_size
    total = await service.count_machines(
        session,
        factory_id=factory_id,
        q=q,
        machine_type=machine_type,
        allowed_factories=allowed,
        include_inactive=include_inactive,
    )
    rows = await service.list_machines(
        session,
        factory_id=factory_id,
        q=q,
        machine_type=machine_type,
        limit=page_size,
        offset=offset,
        allowed_factories=allowed,
        include_inactive=include_inactive,
    )
    return PaginatedResponse(
        items=rows,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{machine_id}/image", responses=READ_ERRORS)
async def get_machine_image(
    machine_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    p = get_principal(request)
    m = await service.get_machine(session, machine_id)
    if not m:
        raise HTTPException(404, "machine not found")
    enforce_factory_access(p, m.factory_id, "read")
    if not m.image_storage_uri:
        raise HTTPException(404, "machine image not found")
    storage = get_storage()
    if not await storage.exists(m.image_storage_uri):
        raise HTTPException(404, "image file not found on storage")
    media_type = _mime_from_storage_uri(m.image_storage_uri) or "image/jpeg"
    return StreamingResponse(
        open_storage_object_async(m.image_storage_uri),
        media_type=media_type,
    )


@router.post("/{machine_id}/image", status_code=204, responses=WRITE_ERRORS)
async def upload_machine_image(
    machine_id: str,
    request: Request,
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
):
    p = get_principal(request)
    m = await service.get_machine(session, machine_id)
    if not m:
        raise HTTPException(404, "machine not found")
    enforce_factory_access(p, m.factory_id, "write")

    raw = await file.read()
    max_bytes = min(settings.max_machine_image_bytes, MAX_MACHINE_IMAGE_BYTES)
    if len(raw) > max_bytes:
        raise HTTPException(413, f"image exceeds max size of {max_bytes} bytes")

    mime = (file.content_type or "").split(";")[0].strip().lower()
    if not mime or not is_allowed_image_mime(mime):
        guessed = guess_image_mime_from_name(file.filename or "")
        mime = guessed or mime
    if not mime or not is_allowed_image_mime(mime):
        raise HTTPException(415, "unsupported image type; use JPEG, PNG, or WebP")

    import io

    uri = await save_machine_image(
        factory_id=m.factory_id,
        machine_id=machine_id,
        mime=mime,
        stream=io.BytesIO(raw),
        old_storage_uri=m.image_storage_uri,
    )
    m.image_storage_uri = uri
    m.image_updated_at = datetime.now(UTC)
    await session.commit()


@router.delete("/{machine_id}/image", status_code=204, responses=WRITE_ERRORS)
async def delete_machine_image(
    machine_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    p = get_principal(request)
    m = await service.get_machine(session, machine_id)
    if not m:
        raise HTTPException(404, "machine not found")
    enforce_factory_access(p, m.factory_id, "write")
    await delete_machine_image_storage(
        m.image_storage_uri,
        factory_id=m.factory_id,
        machine_id=machine_id,
    )
    m.image_storage_uri = None
    m.image_updated_at = None
    await session.commit()


@router.get("/{machine_id}", response_model=MachineOut, responses=READ_ERRORS)
async def get_machine(
    machine_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    p = get_principal(request)
    m = await service.get_machine(session, machine_id)
    if not m:
        raise HTTPException(404, "machine not found")
    enforce_factory_access(p, m.factory_id, "read")
    return m


@router.post("", response_model=MachineOut, status_code=201, responses=WRITE_ERRORS)
async def create_machine(
    payload: MachineCreate,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    p = get_principal(request)
    enforce_factory_access(p, payload.factory_id, "write")
    try:
        return await service.create_machine(session, payload.model_dump())
    except ValueError as exc:
        if "already exists" in str(exc):
            raise HTTPException(409, "machine already exists") from exc
        raise HTTPException(400, "invalid machine data") from exc


@router.patch("/{machine_id}", response_model=MachineOut, responses=READ_ERRORS)
async def update_machine(
    machine_id: str,
    payload: MachinePatch,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    p = get_principal(request)
    m = await service.get_machine(session, machine_id)
    if not m:
        raise HTTPException(404, "machine not found")
    enforce_factory_access(p, m.factory_id, "write")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(m, k, v)
    await session.commit()
    await session.refresh(m)
    return m


@router.delete("/{machine_id}", status_code=204, responses=WRITE_ERRORS)
async def delete_machine(
    machine_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    p = get_principal(request)
    m = await service.get_machine(session, machine_id)
    if not m:
        raise HTTPException(404, "machine not found")
    enforce_factory_access(p, m.factory_id, "write")
    try:
        await service.delete_machine(session, machine_id=machine_id)
    except ValueError as exc:
        if "not found" in str(exc):
            raise HTTPException(404, "machine not found") from exc
        raise HTTPException(409, str(exc)) from exc


@router.post("/{machine_id}/aliases", response_model=AliasOut, status_code=201, responses=READ_ERRORS)
async def add_alias(
    machine_id: str,
    payload: AliasCreate,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    p = get_principal(request)
    m = await service.get_machine(session, machine_id)
    if not m:
        raise HTTPException(404, "machine not found")
    enforce_factory_access(p, m.factory_id, "write")
    return await service.add_machine_alias(
        session, machine_id, payload.alias, payload.source or "manual"
    )
