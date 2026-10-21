"""Rerank pipeline — prefilter → CE → diversify with degraded fallback."""

from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass
from spark.retrieval.deadline import RequestDeadline

from spark.core.config import settings
from spark.core.gpu_sidecar import sidecar_enabled
from spark.core.metrics import rag_doc_rerank_seconds, reranker_degraded_total
from spark.retrieval.degraded_policy import apply_degraded_rerank
from spark.retrieval.degraded_types import DegradedRetrievalPolicy
from spark.retrieval.intent.router import IntentPlan, QueryIntent
from spark.retrieval.rerank.cross_encoder import RerankCacheContext, cross_encoder
from spark.retrieval.rerank.diversify import cross_document_select
from spark.retrieval.rerank.prefilter import prefilter_candidates
from spark.retrieval.common import log
from spark.retrieval.models import RetrievedDoc
from spark.retrieval.scoring import _is_symptom_action_query, _prefers_manual


# Summary / comparison / coverage questions ("สรุป...", "มีอะไรบ้าง", "เปรียบเทียบ
# X กับ Y", "what topics does the manual cover") need evidence breadth rather
# than the single best chunk.
_BROAD_SYNTHESIS_RE = re.compile(
    r"(สรุป|ภาพรวม|ทั้งหมด|มีอะไรบ้าง|มีหัวข้ออะไร|ครอบคลุม|เปรียบเทียบ|ต่างกัน(?:อย่างไร|ยังไง)?|"
    r"เหมือนกัน|ข้อดีข้อเสีย|checklist|เช็คลิสต์|"
    r"summar(?:y|ize|ise)|overview|compare|comparison|difference|list\s+all|what\s+topics|cover)",
    re.IGNORECASE,
)


def _is_broad_synthesis_query(query: str) -> bool:
    return bool(_BROAD_SYNTHESIS_RE.search(query or ""))


@dataclass
class RerankResult:
    docs: list[RetrievedDoc]
    ce_available: bool
    degraded: bool
    latency_ms: float
    policy: DegradedRetrievalPolicy = DegradedRetrievalPolicy.CE_ACTIVE


class RerankPipeline:
    """Latency-bounded rerank orchestrator (Phase 8)."""

    async def apply(
        self,
        query: str,
        docs: list[RetrievedDoc],
        top_k: int,
        *,
        session_id: str | None = None,
        intent_plan: IntentPlan | None = None,
        deadline: RequestDeadline | None = None,
        safety_intent_kind: str | None = None,
    ) -> RerankResult:
        start = time.perf_counter()
        if not docs:
            return RerankResult(
                docs=[],
                ce_available=False,
                degraded=False,
                latency_ms=0.0,
                policy=DegradedRetrievalPolicy.CE_ACTIVE,
            )

        if deadline is not None and deadline.expired():
            log.info("rag_rerank_skipped_deadline", remaining_ms=deadline.remaining_ms())
            from spark.retrieval.safety.safety_intent import detect_safety_intent

            intent = intent_plan.intent if intent_plan else QueryIntent.GENERAL
            safety = safety_intent_kind or detect_safety_intent(query).kind.value
            degraded_docs, policy = apply_degraded_rerank(
                docs[:top_k],
                intent=intent,
                safety_intent_kind=safety,
                ce_available=False,
            )
            return RerankResult(
                docs=degraded_docs,
                ce_available=False,
                degraded=True,
                latency_ms=round((time.perf_counter() - start) * 1000, 2),
                policy=policy,
            )

        # Fast-path: skip CE reranking entirely when disabled (e.g. CPU/MPS dev).
        # Falls back to vector similarity + RRF scores directly.
        if not settings.rag_rerank_enabled:
            log.debug("rag_rerank_disabled", reason="RAG_RERANK_ENABLED=false")
            intent = intent_plan.intent if intent_plan else QueryIntent.GENERAL
            if safety_intent_kind is None:
                from spark.retrieval.safety.safety_intent import detect_safety_intent
                safety = detect_safety_intent(query).kind.value
            else:
                safety = safety_intent_kind
            degraded_docs, policy = apply_degraded_rerank(
                docs[:top_k],
                intent=intent,
                safety_intent_kind=safety,
                ce_available=False,
            )
            return RerankResult(
                docs=degraded_docs,
                ce_available=False,
                degraded=True,
                latency_ms=round((time.perf_counter() - start) * 1000, 2),
                policy=policy,
            )

        docs = prefilter_candidates(docs, top_k)
        prefer_manual = _prefers_manual(query) or _is_symptom_action_query(query)
        prefer_procedure = _is_symptom_action_query(query)

        cache_context = None
        if session_id:
            cache_context = RerankCacheContext(
                session_id=session_id,
                question=query,
                chunk_ids=[str(d.payload.get("chunk_id") or idx) for idx, d in enumerate(docs)],
                generations=[
                    int(d.payload.get("ingest_generation") or 1) for d in docs
                ],
            )

        relevances: list[float] | None = None
        timeout = float(getattr(settings, "rag_rerank_timeout_sec", 5) or 5)
        from spark.core.forge_client import forge_rerank_active

        if sidecar_enabled():
            sidecar_budget = float(getattr(settings, "gpu_sidecar_timeout_sec", 15.0) or 15.0)
            # Long manual chunks (~4k chars) on Jetson need ~0.5–1s/pair; never cap
            # below the sidecar HTTP budget or CE falsely degrades to fusion rank.
            scaled = 8.0 + 0.65 * len(docs)
            timeout = max(timeout, sidecar_budget, scaled)
        elif forge_rerank_active():
            forge_budget = float(getattr(settings, "forge_timeout_sec", 30.0) or 30.0)
            scaled = 8.0 + 0.65 * len(docs)
            timeout = max(timeout, forge_budget, scaled)
        if deadline is not None:
            timeout = min(timeout, max(0.001, deadline.remaining_ms() / 1000.0))
        try:
            relevances = await asyncio.wait_for(
                cross_encoder.score_pairs_async(
                    query,
                    [d.page_content for d in docs],
                    cache_context=cache_context,
                ),
                timeout=timeout,
            )
        except TimeoutError:
            log.warning("rag_rerank_timeout", timeout_sec=timeout, candidates=len(docs))
            reranker_degraded_total.labels(reason="timeout").inc()
            relevances = None

        ce_available = relevances is not None and len(relevances) == len(docs)
        degraded = not ce_available
        intent = intent_plan.intent if intent_plan else QueryIntent.GENERAL
        if safety_intent_kind is None:
            from spark.retrieval.safety.safety_intent import detect_safety_intent

            safety = detect_safety_intent(query).kind.value
        else:
            safety = safety_intent_kind

        select_kwargs = {}
        if intent == QueryIntent.IO_MAPPING:
            select_kwargs = {
                "max_docs": max(settings.rag_max_docs, 3),
                "max_chunks_per_doc": max(settings.rag_max_chunks_per_doc, top_k),
            }
        elif intent == QueryIntent.DRAWING:
            select_kwargs = {
                "max_docs": max(settings.rag_max_docs, 3),
                "max_chunks_per_doc": max(settings.rag_max_chunks_per_doc, min(top_k, 12)),
            }
        elif intent in (QueryIntent.ALARM_DIAGNOSTIC, QueryIntent.PROCEDURE):
            # Alarm/procedure answers about one machine commonly span several
            # chunks of the *same* manual (alarm name, trigger temperature, LED
            # blink count, error code, remedy steps live in separate table rows/
            # chunks). The default 2 chunks/doc drops needed facts and makes the
            # model falsely report a value as "not documented" — give multi-fact
            # questions room within the single relevant manual.
            select_kwargs = {
                "max_chunks_per_doc": max(settings.rag_max_chunks_per_doc, min(top_k, 6)),
            }
        elif _is_broad_synthesis_query(query):
            # Summaries / comparisons / "what does this doc cover" questions need
            # breadth: several chunks of one doc (summary) or several docs
            # (comparison). The default 2 chunks/doc starves them into partial,
            # misleading answers.
            select_kwargs = {
                "max_docs": max(settings.rag_max_docs, 3),
                "max_chunks_per_doc": max(settings.rag_max_chunks_per_doc, min(top_k, 6)),
            }

        if ce_available:
            result = cross_document_select(
                query,
                docs,
                top_k=top_k,
                prefer_manual=prefer_manual,
                prefer_procedure=prefer_procedure,
                precomputed_scores=relevances,
                **select_kwargs,
            )
            policy = DegradedRetrievalPolicy.CE_ACTIVE
        else:
            reranker_degraded_total.labels(reason="service_unavailable").inc()
            degraded_docs, policy = apply_degraded_rerank(
                list(docs),
                intent=intent,
                safety_intent_kind=safety,
                ce_available=False,
            )
            # CE timed out or was unavailable — reuse upstream fusion scores.
            # cross_document_select without precomputed_scores would synchronously
            # call score_pairs() and, on sidecar failure, load the CPU model for
            # minutes even though we already decided to degrade.
            fusion_scores = [
                float(getattr(d, "fusion_score", None) or d.score) for d in degraded_docs
            ]
            result = cross_document_select(
                query,
                degraded_docs,
                top_k=top_k,
                prefer_manual=prefer_manual,
                prefer_procedure=prefer_procedure,
                precomputed_scores=fusion_scores,
                **select_kwargs,
            )

        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        rag_doc_rerank_seconds.observe(time.perf_counter() - start)
        log.info(
            "rag_rerank_complete",
            ce_available=ce_available,
            degraded=degraded,
            returned=len(result),
            latency_ms=latency_ms,
            intent=intent.value if intent_plan else None,
            policy=policy.value,
        )
        return RerankResult(
            docs=result,
            ce_available=ce_available,
            degraded=degraded,
            latency_ms=latency_ms,
            policy=policy,
        )


_default_pipeline: RerankPipeline | None = None


def get_rerank_pipeline() -> RerankPipeline:
    global _default_pipeline
    if _default_pipeline is None:
        _default_pipeline = RerankPipeline()
    return _default_pipeline
