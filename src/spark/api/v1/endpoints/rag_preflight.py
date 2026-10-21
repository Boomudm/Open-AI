"""Query pre-flight — policy scan without retrieval (Phase 14)."""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from spark.api.openapi_responses import READ_ERRORS
from spark.core.security import get_principal
from spark.retrieval.safety.query_policy import scan_query
from spark.retrieval.safety.safety_intent import detect_safety_intent

router = APIRouter(prefix="/rag", tags=["RAG"])


class RagPreflightRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=4000)
    factory_id: str | None = None


class RagPreflightResponse(BaseModel):
    accepted: bool
    reasons: list[str] = Field(default_factory=list)
    latency_tier: str = "standard"
    estimated_cost: str = "low"
    safety_intent: str = "none"
    query_policy_action: str = "allow"


@router.post("/preflight", response_model=RagPreflightResponse, responses=READ_ERRORS)
async def rag_preflight(
    body: RagPreflightRequest,
    request: Request,
) -> RagPreflightResponse:
    get_principal(request)
    reasons: list[str] = []

    policy = scan_query(body.question)
    safety = detect_safety_intent(body.question)

    if policy.action == "block":
        reasons.append(policy.reason or "query blocked by policy")

    latency_tier = "safety_strict" if safety.kind.value != "none" else "standard"
    estimated_cost = "high" if len(body.question) > 500 or safety.kind.value != "none" else "low"

    return RagPreflightResponse(
        accepted=len(reasons) == 0,
        reasons=reasons,
        latency_tier=latency_tier,
        estimated_cost=estimated_cost,
        safety_intent=safety.kind.value,
        query_policy_action=policy.action,
    )
