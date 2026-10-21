from __future__ import annotations


from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from spark.api.openapi_responses import WRITE_ERRORS
from spark.core.database import get_session
from spark.core.security import enforce_rag_filter_access, get_principal
from spark.schemas.rag import (
    AskResponse,
    RAGQuery,
    RetrievalReportModel,
    SystemDegradationModel,
    sources_to_refs,
)
from spark.services.document_access_service import allowed_doc_ids_for_principal
from spark.services.rag_service import RAGFilter, rag_service

router = APIRouter(prefix="/rag", tags=["RAG"])


def _to_filter(model) -> RAGFilter:
    if model is None:
        return RAGFilter()
    return RAGFilter(**model.model_dump())


@router.post("/query", response_model=AskResponse, responses=WRITE_ERRORS)
async def query(
    req: RAGQuery,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    p = get_principal(request)
    rf = _to_filter(req.filter)
    from spark.core.qdrant_strategy import validate_factory_id_for_retrieval

    try:
        validate_factory_id_for_retrieval(rf.factory_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    await enforce_rag_filter_access(session, p, rf)
    from spark.retrieval.safety.admission import rag_admission_guard

    raw_ids = await allowed_doc_ids_for_principal(session, p)
    allowed_doc_ids = None if raw_ids is None else [str(i) for i in raw_ids]
    async with rag_admission_guard(
        rf.factory_id,
        user_id=str(p.user_id) if p.user_id else None,
    ):
        result = await rag_service.query(
            question=req.question,
            rf=rf,
            top_k=req.top_k,
            allowed_doc_ids=allowed_doc_ids,
            allow_scope_broadening=req.allow_scope_broadening,
        )
    report = None
    if result.retrieval_report:
        report = RetrievalReportModel(**result.retrieval_report)
    degradation = None
    if result.system_degradation:
        degradation = SystemDegradationModel(**result.system_degradation)
    return AskResponse(
        answer=result.answer,
        sources=sources_to_refs(result.sources),
        used_filters=result.used_filters,
        intent=result.intent,
        fallback_level=result.fallback_level,
        retrieval_report=report,
        system_degradation=degradation,
    )


@router.get("/health", responses={200: {"content": {"application/json": {"example": {"status": "ok", "service": "rag"}}}}})
async def health():
    return {"status": "ok", "service": "rag"}
