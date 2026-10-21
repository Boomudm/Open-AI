from __future__ import annotations

from fastapi import APIRouter

from spark.api.v1.endpoints import (
    admin,
    admin_data_sources,
    api_keys,
    audit_export,
    auth,
    chat,
    document_release,
    documents,
    factories,
    feedback,
    ingest,
    ingest_preflight,
    job_positions,
    jobs,
    machines,
    rag,
    rag_preflight,
    streams,
    system_admin,
)

router = APIRouter(prefix="/api/v1")
router.include_router(audit_export.router)
router.include_router(auth.router)
router.include_router(streams.router)
router.include_router(factories.router)
router.include_router(machines.router)
router.include_router(admin.router)
router.include_router(admin_data_sources.router)
router.include_router(api_keys.router)
router.include_router(job_positions.router)
router.include_router(documents.router)
router.include_router(document_release.router)
router.include_router(feedback.router)
router.include_router(ingest.router)
router.include_router(ingest_preflight.router)
router.include_router(jobs.router)
router.include_router(rag.router)
router.include_router(rag_preflight.router)
router.include_router(chat.router)
router.include_router(system_admin.router)
