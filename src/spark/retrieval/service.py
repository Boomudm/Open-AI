from __future__ import annotations

import re
import time
from dataclasses import asdict, dataclass, field, replace
from typing import Any, AsyncIterator

from langchain_ollama import ChatOllama

from .context_budget import (
    build_rag_context_budget,
    fit_docs_to_budget,
    log_context_budget_applied,
)
from spark.core.config import settings
from spark.core.lazy_singleton import lazy_singleton
from spark.core.llm_client import get_chat_llm
from spark.core.metrics import (
    context_trim_total,
    rag_fallback_level_histogram,
    rag_query_seconds,
    rag_query_total,
    rag_scope_broadened_total,
)
from spark.core.rag_observability import rag_answer_produced_fields
from spark.retrieval.engine import RetrievalEngine
from spark.retrieval.deadline import RequestDeadline
from spark.retrieval.kernel import RAGKernelInput, RAGKernelOutput, get_rag_kernel
from spark.retrieval.lexical import retrieve_lexical_candidates
from spark.ingestion.embedder import Embedder

from .common import log
from .constants import NO_DATA_ANSWER, UNAVAILABLE_ANSWER
from spark.retrieval.safety.circuit_breaker import (
    RAGCircuitMode,
    record_rag_outcome_async,
    resolve_rag_circuit_decision,
)
from spark.retrieval.safety.fallback_ladder import FallbackContext, run_fallback_ladder
from spark.generation.pipeline import grounded_generate_with_enforced_citations
from spark.generation.policy import resolve_generation_policy
from .models import (
    RAGFilter,
    RAGResult,
    RAGStreamPhaseMeta,
    RetrievedDoc,
    _payload_to_source,
    cited_docs_to_sources,
)
from .retrieval_snapshot import build_retrieval_snapshot
from spark.retrieval.intent.router import IntentRouter, QueryIntent
from spark.retrieval.intent import features
from .scoring import (
    _filter_machine_conflicts,
    _has_sufficient_evidence,
    _retrieval_sources_from_docs,
    should_refuse_rag_answer,
)
from .synthesis import (
    _order_docs_for_context,
    _select_sources_for_display,
)
from spark.retrieval.safety.safety_intent import SafetyIntentKind, detect_safety_intent, requires_strict_retrieval

from .tuning import RagFusionConfig, RagTuningContext


def _observe_rag_query_metrics(
    *,
    fallback_level: int,
    started_at: float,
    intent: str,
    degraded: bool,
) -> None:
    """Record completed query counters and latency with semantic labels."""
    label = str(fallback_level)
    intent_label = (intent or "unknown").strip() or "unknown"
    degraded_label = "true" if degraded else "false"
    rag_query_total.labels(label).inc()
    if fallback_level > 0:
        rag_scope_broadened_total.labels(label).inc()
    rag_query_seconds.labels(intent_label, label, degraded_label).observe(
        time.perf_counter() - started_at
    )


async def _load_factory_machine_ids(factory_id: str | None) -> set[str] | None:
    if not factory_id:
        return None
    from sqlalchemy import select

    from spark.core.database import AsyncSessionLocal
    from spark.db.models.org import Machine

    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(
                select(Machine.machine_id).where(
                    Machine.factory_id == factory_id,
                    Machine.is_active.is_(True),
                )
            )
        ).scalars().all()
    return {str(row) for row in rows if row}


@dataclass
class _RetrievalBundle:
    docs: list[RetrievedDoc]
    fallback_level: int
    used_filters: dict[str, Any]
    top_doc_score: float
    scope_rf: RAGFilter
    retrieval_report: dict[str, Any] | None = None
    clarification_suggested: bool = False


@dataclass
class _EarlyRAGResult:
    result: RAGResult
    docs: list[RetrievedDoc] = field(default_factory=list)


_ANSWER_CITATION_RE = re.compile(r"\[chunk_id:[^\]]+\]", re.IGNORECASE)
_ANSWER_REF_TRAILER_RE = re.compile(r"อ้างอิง:.*$", re.DOTALL)
_REFUSAL_START_RE = re.compile(
    r"^\s*(?:ขออภัย\S{0,10}\s*)?(?:Neo\s*)?"
    r"(?:ไม่พบข้อมูล|ยังไม่พบข้อมูล|ไม่พบคำตอบ|ไม่มีข้อมูล|"
    r"ไม่มีการระบุ|ไม่ได้ระบุ|ไม่สามารถระบุ|ไม่ปรากฏ)"
)


def _is_pure_refusal_answer(answer: str) -> bool:
    """True when the answer, minus citations/reference trailer, is just a
    refusal ("ไม่พบข้อมูลในระบบ ...") — the LLM sometimes cites a chunk on its
    refusal sentence, which lets it pass citation validation as 'verified'."""
    body = _ANSWER_CITATION_RE.sub("", answer or "")
    body = _ANSWER_REF_TRAILER_RE.sub("", body).strip()
    return bool(_REFUSAL_START_RE.match(body)) and len(body) <= 220


async def _generate_under_circuit_open(
    question: str,
    ordered_docs: list[RetrievedDoc],
):
    """Circuit-open generation — never answer from documents without the LLM."""
    from spark.generation.types import GroundedGenerateResult

    if not ordered_docs:
        return GroundedGenerateResult(
            answer=NO_DATA_ANSWER,
            cited_docs=[],
            answer_path="no_data",
            citations_verified=False,
        )
    return GroundedGenerateResult(
        answer=UNAVAILABLE_ANSWER,
        cited_docs=[],
        answer_path="system_degraded",
        citations_verified=False,
    )


class RAGService:
    def __init__(self) -> None:
        self._llm: ChatOllama | None = None
        self._embedder: Embedder | None = None
        self._retrieval_engine: RetrievalEngine | None = None
        self._last_retrieval_report: dict[str, Any] | None = None
        self._last_rerank_degraded: bool = False
        self._last_rerank_policy: str = "ce_active"
        self._force_degraded_no_llm: bool = False
        self._force_rerank_circuit_degraded: bool = False

    def _sparse_available_from_report(self) -> bool:
        report = self._last_retrieval_report or {}
        encoder_id = str(report.get("sparse_encoder_id") or "")
        if not encoder_id or encoder_id == "none":
            return False
        return "embed_failed" not in (report.get("degraded_reasons") or [])

    def _degradation_flags_from_report(self) -> tuple[bool, bool]:
        report = self._last_retrieval_report or {}
        reasons = report.get("degraded_reasons") or []
        return "embed_failed" in reasons, "lexical_failed" in reasons

    def _build_system_degradation(self, *, fail_closed: bool = False) -> dict[str, Any]:
        from spark.contracts.degradation_contract import from_retrieval_flags

        embed_failed, lexical_failed = self._degradation_flags_from_report()
        return from_retrieval_flags(
            embed_failed=embed_failed,
            lexical_failed=lexical_failed,
            rerank_degraded=self._last_rerank_degraded,
            rerank_degraded_policy=self._last_rerank_policy,
            sparse_available=self._sparse_available_from_report(),
            fail_closed=fail_closed,
        ).to_dict()

    @staticmethod
    def _intent_plan_snapshot(plan: Any | None) -> dict[str, Any] | None:
        if plan is None:
            return None
        return {
            "intent": plan.intent.value,
            "dense_weight": plan.dense_weight,
            "lexical_weight": plan.lexical_weight,
            "document_type_hint": plan.document_type_hint,
            "min_rerank_score": plan.min_rerank_score,
            "strict_document_type_filter": plan.strict_document_type_filter,
            "weight_version": plan.weight_version,
        }

    def _intent_label_for_metrics(self) -> str:
        plan = self.retrieval_engine.last_intent_plan
        if plan is not None:
            return plan.intent.value
        report = self._last_retrieval_report or {}
        return str(report.get("intent") or "unknown")

    def _degraded_for_metrics(self) -> bool:
        report = self._last_retrieval_report or {}
        return bool(report.get("degraded") or self._last_rerank_degraded)

    def _observe_query_metrics(self, *, fallback_level: int, started_at: float) -> None:
        _observe_rag_query_metrics(
            fallback_level=fallback_level,
            started_at=started_at,
            intent=self._intent_label_for_metrics(),
            degraded=self._degraded_for_metrics(),
        )

    @property
    def retrieval_engine(self) -> RetrievalEngine:
        if self._retrieval_engine is None:
            self._retrieval_engine = RetrievalEngine(
                embedder=self.embedder,
                resolve_fusion_config=self._resolve_fusion_config,
                resolve_lexical_engine=self._resolve_lexical_engine,
                apply_rerank=self._apply_retrieval_rerank_async,
            )
        return self._retrieval_engine

    @retrieval_engine.setter
    def retrieval_engine(self, value: RetrievalEngine) -> None:
        self._retrieval_engine = value

    @property
    def embedder(self) -> Embedder:
        if self._embedder is None:
            self._embedder = Embedder.get()
        return self._embedder

    @embedder.setter
    def embedder(self, value: Embedder) -> None:
        self._embedder = value
        self._retrieval_engine = None

    async def _resolve_lexical_engine(self, rf: RAGFilter):
        from spark.core.database import AsyncSessionLocal
        from spark.core.production_profile import RemediationFlags

        flags = RemediationFlags.from_settings()
        if rf.factory_id:
            from spark.services.factory_config_service import factory_config_service

            async with AsyncSessionLocal() as session:
                factory_cfg = await factory_config_service.resolve(session, rf.factory_id)
            flags = RemediationFlags.for_factory(factory_cfg)
        return flags.lexical_engine

    async def _resolve_fusion_config(self, rf: RAGFilter):
        from spark.core.database import AsyncSessionLocal
        from spark.services.factory_config_service import factory_config_service

        if not rf.factory_id:
            return RagFusionConfig.from_factory_config({})
        async with AsyncSessionLocal() as session:
            factory_cfg = await factory_config_service.resolve(session, rf.factory_id)
        return RagFusionConfig.from_factory_config(factory_cfg)

    async def _retrieve_postgres_lexical_candidates(
        self,
        query: str,
        rf: RAGFilter,
        top_k: int,
        allowed_doc_ids: list[str] | None = None,
    ) -> list[RetrievedDoc]:
        engine = await self._resolve_lexical_engine(rf)
        return await retrieve_lexical_candidates(
            query,
            rf,
            top_k,
            allowed_doc_ids=allowed_doc_ids,
            engine=engine,
        )

    async def _retrieve_lexical_candidates(
        self,
        query: str,
        rf: RAGFilter,
        top_k: int,
        allowed_doc_ids: list[str] | None = None,
    ) -> list[RetrievedDoc]:
        from spark.retrieval.intent.glossary import expand_lexical_variants

        engine = await self._resolve_lexical_engine(rf)
        try:
            return await self._retrieve_postgres_lexical_candidates(
                expand_lexical_variants(query),
                rf,
                top_k,
                allowed_doc_ids=allowed_doc_ids,
            )
        except Exception as exc:
            log.error(
                "rag_postgres_lexical_failed",
                error=str(exc)[:500],
                engine=engine,
                factory_id=rf.factory_id,
                exc_info=True,
            )
            from spark.core.metrics import rag_lexical_degraded_total

            rag_lexical_degraded_total.labels(engine=engine, reason=type(exc).__name__).inc()
            return []

    async def _retrieve(
        self,
        query: str,
        rf: RAGFilter,
        top_k: int,
        allowed_doc_ids: list[str] | None = None,
        *,
        session_id: str | None = None,
        follow_up: bool = False,
        last_retrieved_chunk_ids: list[str] | None = None,
        deadline: RequestDeadline | None = None,
        evidence_age_turns: int | None = None,
    ) -> list[RetrievedDoc]:
        docs, report = await self.retrieval_engine.retrieve(
            query,
            rf,
            top_k,
            allowed_doc_ids=allowed_doc_ids,
            session_id=session_id,
            follow_up=follow_up,
            last_retrieved_chunk_ids=last_retrieved_chunk_ids,
            deadline=deadline,
            evidence_age_turns=evidence_age_turns,
        )
        self._last_retrieval_report = report.to_dict()
        return docs

    async def _apply_retrieval_rerank_async(
        self,
        query: str,
        docs: list[RetrievedDoc],
        top_k: int,
        *,
        session_id: str | None = None,
        intent_plan=None,
        deadline: RequestDeadline | None = None,
    ) -> list[RetrievedDoc]:
        if self._force_rerank_circuit_degraded:
            return self._apply_retrieval_rerank(
                query,
                docs,
                top_k,
                intent_plan=intent_plan,
            )

        from spark.retrieval.degraded_types import DegradedRetrievalPolicy
        from spark.retrieval.rerank.pipeline import get_rerank_pipeline
        from spark.retrieval.safety.safety_intent import detect_safety_intent

        result = await get_rerank_pipeline().apply(
            query,
            docs,
            top_k,
            session_id=session_id,
            intent_plan=intent_plan,
            safety_intent_kind=detect_safety_intent(query).kind.value,
            deadline=deadline,
        )
        self._last_rerank_degraded = result.degraded
        self._last_rerank_policy = result.policy.value
        self._force_degraded_no_llm = result.policy == DegradedRetrievalPolicy.CE_TIMEOUT_EXTRACTIVE_ONLY
        if result.degraded and self._last_retrieval_report is not None:
            report = dict(self._last_retrieval_report)
            reasons = list(report.get("degraded_reasons") or [])
            if "rerank_ce_unavailable" not in reasons:
                reasons.append("rerank_ce_unavailable")
            report["degraded"] = True
            report["degraded_reasons"] = reasons
            report["rerank_degraded"] = True
            report["rerank_degraded_policy"] = result.policy.value
            self._last_retrieval_report = report
        return result.docs

    def _cap_rerank_candidates(
        self, docs: list[RetrievedDoc], top_k: int
    ) -> list[RetrievedDoc]:
        from spark.retrieval.rerank.prefilter import prefilter_candidates

        return prefilter_candidates(docs, top_k)

    def _apply_retrieval_rerank(
        self,
        query: str,
        docs: list[RetrievedDoc],
        top_k: int,
        *,
        prefer_manual: bool | None = None,
        prefer_procedure: bool | None = None,
        intent_plan=None,
    ) -> list[RetrievedDoc]:
        """Sync degraded path — fusion order without async CE."""
        from spark.retrieval.degraded_policy import apply_degraded_rerank
        from spark.retrieval.degraded_types import DegradedRetrievalPolicy
        from spark.retrieval.intent.router import QueryIntent
        from spark.retrieval.rerank.diversify import cross_document_select
        from spark.retrieval.scoring import _is_symptom_action_query, _prefers_manual
        from spark.retrieval.safety.safety_intent import detect_safety_intent

        if not docs:
            return []
        docs = self._cap_rerank_candidates(docs, top_k)
        intent = intent_plan.intent if intent_plan else QueryIntent.GENERAL
        degraded_docs, policy = apply_degraded_rerank(
            list(docs),
            intent=intent,
            safety_intent_kind=detect_safety_intent(query).kind.value,
            ce_available=False,
        )
        self._last_rerank_degraded = True
        self._last_rerank_policy = policy.value
        self._force_degraded_no_llm = policy == DegradedRetrievalPolicy.CE_TIMEOUT_EXTRACTIVE_ONLY
        return cross_document_select(
            query,
            degraded_docs,
            top_k=top_k,
            prefer_manual=(
                prefer_manual
                if prefer_manual is not None
                else (_prefers_manual(query) or _is_symptom_action_query(query))
            ),
            prefer_procedure=(
                prefer_procedure
                if prefer_procedure is not None
                else _is_symptom_action_query(query)
            ),
        )

    def _passes_relevance(
        self,
        docs: list[RetrievedDoc],
        *,
        min_max_score: float | None = None,
        min_avg_score: float | None = None,
        question: str | None = None,
        tuning=None,
        intent_plan=None,
        circuit_enabled: bool = False,
        factory_id: str | None = None,
    ) -> bool:
        from spark.retrieval.degraded_types import DegradedRetrievalPolicy
        from spark.retrieval.rerank.gate import passes_authoritative_relevance_gate

        degraded_policy = None
        if self._last_rerank_degraded:
            try:
                degraded_policy = DegradedRetrievalPolicy(self._last_rerank_policy)
            except ValueError:
                degraded_policy = DegradedRetrievalPolicy.CE_TIMEOUT_FUSION_RANK

        return passes_authoritative_relevance_gate(
            docs,
            min_max_score=min_max_score,
            min_avg_score=min_avg_score,
            question=question,
            tuning=tuning,
            intent_plan=intent_plan,
            circuit_enabled=circuit_enabled,
            degraded=self._last_rerank_degraded,
            degraded_policy=degraded_policy,
            factory_id=factory_id,
        )

    def _filter_latest_revision(self, docs: list[RetrievedDoc]) -> list[RetrievedDoc]:
        by_doc: dict[str | None, RetrievedDoc] = {}
        for doc in docs:
            doc_id = doc.payload.get("doc_id")
            current = by_doc.get(doc_id)
            if current is None or self._revision_sort_key(doc) > self._revision_sort_key(current):
                by_doc[doc_id] = doc
        return list(by_doc.values())

    def _filter_exact_revision(
        self,
        docs: list[RetrievedDoc],
        revision: str | None,
    ) -> list[RetrievedDoc]:
        if not revision:
            return docs
        from spark.services.document_revision import parse_revision

        _, normalized = parse_revision(revision)
        target = (normalized or revision).strip().lower()
        filtered = [
            doc
            for doc in docs
            if str(doc.payload.get("revision") or "").strip().lower() in {target, revision.strip().lower()}
        ]
        return filtered

    @staticmethod
    def _revision_sort_key(doc: RetrievedDoc) -> int:
        from spark.services.document_revision import parse_revision

        payload_key = doc.payload.get("revision_sort_key")
        if payload_key is not None:
            try:
                return int(payload_key)
            except (TypeError, ValueError):
                pass
        sort_key, _ = parse_revision(doc.payload.get("revision"))
        return sort_key

    def _get_llm(self) -> ChatOllama:
        if self._llm is None:
            self._llm = get_chat_llm()  # type: ignore[assignment]
        return self._llm
    async def _rag_circuit_enabled(self, rf: RAGFilter | None) -> bool:
        from spark.core.database import AsyncSessionLocal
        from spark.core.production_profile import ProductionProfile
        from spark.services.factory_config_service import factory_config_service

        if rf and rf.factory_id:
            async with AsyncSessionLocal() as session:
                factory_cfg = await factory_config_service.resolve(session, rf.factory_id)
            return ProductionProfile.for_factory(factory_cfg).rag_circuit_enabled
        return ProductionProfile.from_settings().rag_circuit_enabled

    async def execute_sync(self, inp: RAGKernelInput) -> RAGKernelOutput:
        """Kernel executor — sync RAG path with circuit breaker and guardrails."""
        deadline = RequestDeadline.from_settings(started_at=inp.deadline_started_at)
        _start = deadline.started_at
        was_probe = inp.circuit_mode == RAGCircuitMode.HALF_OPEN.value
        from spark.observability.otel_tracing import start_span

        try:
            with start_span("rag.query", stream=False, factory_id=(inp.rf.factory_id if inp.rf else None)):
                result = await self._query_impl(
                    inp.question,
                    inp.rf,
                    inp.top_k,
                    _start,
                    inp.allowed_doc_ids,
                    synthesis_question=inp.synthesis_question,
                    chat_history=inp.chat_history,
                    tuning=inp.tuning,
                    allow_scope_broadening=inp.allow_scope_broadening,
                    session_id=inp.session_id,
                    skip_llm=inp.skip_llm,
                    force_rerank_degraded=inp.force_rerank_degraded,
                    circuit_enabled=inp.circuit_enabled,
                    safety_intent_kind=inp.safety_intent,
                    circuit_mode=inp.circuit_mode,
                    question_raw=inp.question_raw,
                    rewrite_meta=inp.rewrite_meta,
                    session_slots=inp.session_slots,
                    follow_up=inp.follow_up,
                    last_retrieved_chunk_ids=inp.last_retrieved_chunk_ids,
                    deadline=deadline,
                )
            await record_rag_outcome_async(
                "success",
                enabled=inp.circuit_enabled,
                factory_id=inp.rf.factory_id if inp.rf else None,
                was_half_open_probe=was_probe,
            )
            return RAGKernelOutput(result=result, events=[])
        except Exception as exc:
            log.error("rag_query_failed", error=str(exc)[:500], exc_info=True)
            await record_rag_outcome_async(
                "unhandled",
                enabled=inp.circuit_enabled,
                factory_id=inp.rf.factory_id if inp.rf else None,
            )
            log.info(
                "rag_answer_produced",
                **rag_answer_produced_fields(
                    answer_path="service_unavailable",
                    retrieval_sources=[],
                    fallback_level=0,
                    top_doc_score=0.0,
                    sources_count=0,
                    latency_ms=round((time.perf_counter() - _start) * 1000, 2),
                    question=inp.question,
                    safety_intent=inp.safety_intent,
                    circuit_mode=inp.circuit_mode,
                ),
            )
            return RAGKernelOutput(
                result=RAGResult(
                    answer=UNAVAILABLE_ANSWER,
                    sources=[],
                    used_filters={
                        "answer_path": "service_unavailable",
                        "retrieval_sources": [],
                    },
                    fallback_level=0,
                    intent="factual",
                    answer_path="service_unavailable",
                    retrieval_sources=[],
                ),
                events=[],
            )

    async def execute_stream(self, inp: RAGKernelInput) -> AsyncIterator[str | RAGResult | RAGStreamPhaseMeta]:
        """Kernel executor — streaming RAG path with circuit parity."""
        deadline = RequestDeadline.from_settings(started_at=inp.deadline_started_at)
        _start = deadline.started_at
        was_probe = inp.circuit_mode == RAGCircuitMode.HALF_OPEN.value
        try:
            async for item in self._query_stream_impl(
                inp.question,
                inp.rf,
                inp.top_k,
                _start,
                inp.allowed_doc_ids,
                synthesis_question=inp.synthesis_question,
                chat_history=inp.chat_history,
                tuning=inp.tuning,
                skip_llm=inp.skip_llm,
                force_rerank_degraded=inp.force_rerank_degraded,
                circuit_enabled=inp.circuit_enabled,
                safety_intent_kind=inp.safety_intent,
                circuit_mode=inp.circuit_mode,
                question_raw=inp.question_raw,
                rewrite_meta=inp.rewrite_meta,
                session_slots=inp.session_slots,
                follow_up=inp.follow_up,
                last_retrieved_chunk_ids=inp.last_retrieved_chunk_ids,
                allow_scope_broadening=inp.allow_scope_broadening,
                session_id=inp.session_id,
                deadline=deadline,
                cancel_event=inp.cancel_event,
            ):
                yield item
            await record_rag_outcome_async(
                "success",
                enabled=inp.circuit_enabled,
                factory_id=inp.rf.factory_id if inp.rf else None,
                was_half_open_probe=was_probe,
            )
        except Exception as exc:
            log.error("rag_query_stream_failed", error=str(exc)[:500], exc_info=True)
            await record_rag_outcome_async(
                "unhandled",
                enabled=inp.circuit_enabled,
                factory_id=inp.rf.factory_id if inp.rf else None,
            )
            yield RAGResult(
                answer=UNAVAILABLE_ANSWER,
                sources=[],
                used_filters={"answer_path": "service_unavailable"},
                fallback_level=0,
                intent="factual",
                answer_path="service_unavailable",
            )

    def _build_kernel_input(
        self,
        question: str,
        rf: RAGFilter | None,
        top_k: int,
        allowed_doc_ids: list[str] | None,
        *,
        synthesis_question: str | None,
        chat_history: list[tuple[str, str]] | None,
        tuning: RagTuningContext | None,
        allow_scope_broadening: bool,
        session_id: str | None,
        question_raw: str | None,
        rewrite_meta: dict[str, Any] | None,
        session_slots: dict[str, Any] | None,
        follow_up: bool,
        last_retrieved_chunk_ids: list[str] | None,
        stream: bool,
        deadline_started_at: float | None = None,
        cancel_event: Any | None = None,
    ) -> RAGKernelInput:
        return RAGKernelInput(
            question=question,
            rf=rf,
            top_k=top_k,
            allowed_doc_ids=allowed_doc_ids,
            synthesis_question=synthesis_question,
            chat_history=chat_history,
            tuning=tuning,
            allow_scope_broadening=allow_scope_broadening,
            session_id=session_id,
            question_raw=question_raw,
            rewrite_meta=rewrite_meta,
            session_slots=session_slots,
            follow_up=follow_up,
            last_retrieved_chunk_ids=last_retrieved_chunk_ids,
            stream=stream,
            deadline_started_at=deadline_started_at,
            cancel_event=cancel_event,
        )

    async def query(
        self,
        question: str,
        rf: RAGFilter | None = None,
        top_k: int = 6,
        allowed_doc_ids: list[str] | None = None,
        *,
        synthesis_question: str | None = None,
        chat_history: list[tuple[str, str]] | None = None,
        tuning: RagTuningContext | None = None,
        allow_scope_broadening: bool = False,
        session_id: str | None = None,
        question_raw: str | None = None,
        rewrite_meta: dict[str, Any] | None = None,
        session_slots: dict[str, Any] | None = None,
        follow_up: bool = False,
        last_retrieved_chunk_ids: list[str] | None = None,
    ) -> RAGResult:
        from spark.retrieval.preprocess.adaptive import classify_retrieval_need
        from spark.retrieval.preprocess.compound import (
            ambiguous_action_answer,
            classify_subquestion,
            document_scope_clarification_answer,
            external_live_answer,
            factory_operation_answer,
            general_support_answer,
            machine_context_answer,
            is_external_live_question,
            is_policy_question,
            is_sensitive_request,
            safety_emergency_answer,
            safety_procedure_answer,
            sensitive_request_answer,
            out_of_scope_answer,
            policy_answer,
            scope_clarification_answer,
            split_compound_question,
        )

        # The configured query blocklist (LOTO-bypass, instruction override)
        # is the fail-closed layer and must outrank every convenience
        # intercept below — a "skip LOTO ได้ไหม" must get the policy block,
        # not a keyword classifier's canned advice.
        early_block = self._early_policy_block(question)
        if early_block is not None:
            return early_block

        adaptive = classify_retrieval_need(question)
        if adaptive.decision != "retrieve" and adaptive.direct_answer:
            log.info("adaptive_skip", decision=adaptive.decision, category=adaptive.answer_category)
            return RAGResult(
                answer=adaptive.direct_answer,
                sources=[],
                used_filters={"answer_path": adaptive.decision, "adaptive_category": adaptive.answer_category},
                fallback_level=0,
                intent="chitchat",
                answer_path=adaptive.decision,
                retrieval_sources=[],
            )

        rf = rf or RAGFilter()
        known_machine_ids = await _load_factory_machine_ids(rf.factory_id)
        if is_policy_question(question):
            return RAGResult(
                answer=policy_answer(question),
                sources=[],
                used_filters={"answer_path": "policy_direct"},
                fallback_level=0,
                intent="policy",
                top_doc_score=0.0,
                answer_path="policy_direct",
                retrieval_sources=[],
            )

        if is_sensitive_request(question):
            return RAGResult(
                answer=sensitive_request_answer(question),
                sources=[],
                used_filters={"answer_path": "sensitive_refusal"},
                fallback_level=0,
                intent="policy",
                top_doc_score=0.0,
                answer_path="sensitive_refusal",
                retrieval_sources=[],
            )

        if rewrite_meta is None or not rewrite_meta.get("compound_child"):
            # Split what the USER asked, not the rewritten form. The follow-up
            # rewrite merges the previous turn into the current one ("alarm 26h
            # คืออะไร" + "แล้วสาเหตุของมันคืออะไร"), and splitting that merge just
            # tears it back into the two turns it was built from — answering the
            # already-answered question again and running the whole pipeline
            # twice for one follow-up. Retrieval still uses the rewritten
            # `question` below; only topic counting keys off the raw utterance.
            parts = split_compound_question(question_raw or question)
            if len(parts) >= 2:
                answers: list[str] = []
                sources: list[dict[str, Any]] = []
                top_doc_score = 0.0
                fallback_level = 0
                child_paths: list[str] = []
                needs_scope_parts: list[str] = []
                needs_document_scope_parts: list[str] = []
                external_parts: list[str] = []
                for idx, part in enumerate(parts, start=1):
                    classified = classify_subquestion(
                        part, machine_id=rf.machine_id, known_machine_ids=known_machine_ids
                    )
                    if classified.kind == "chitchat":
                        child_adaptive = classify_retrieval_need(part)
                        text = child_adaptive.direct_answer or "สวัสดีครับ"
                        child_paths.append("skip_chitchat")
                    elif classified.kind == "external_live":
                        text = external_live_answer(part, compact=True)
                        external_parts.append(part)
                        child_paths.append("external_live_unsupported")
                    elif classified.kind == "policy":
                        text = policy_answer(part, compact=True)
                        child_paths.append("policy_direct")
                    elif classified.kind == "sensitive":
                        text = sensitive_request_answer(part, compact=True)
                        child_paths.append("sensitive_refusal")
                    elif classified.kind == "safety_emergency":
                        text = safety_emergency_answer(part, compact=True)
                        child_paths.append("safety_emergency")
                    elif classified.kind == "safety_procedure":
                        text = safety_procedure_answer(part, compact=True)
                        child_paths.append("safety_procedure")
                    elif classified.kind == "factory_operation":
                        text = factory_operation_answer(part, compact=True)
                        child_paths.append("factory_operation_clarification")
                    elif classified.kind == "machine_context":
                        text = machine_context_answer(part, compact=True)
                        child_paths.append("machine_context_clarification")
                    elif classified.kind == "out_of_scope":
                        text = out_of_scope_answer(part, compact=True)
                        child_paths.append("out_of_scope")
                    elif classified.kind == "ambiguous_action":
                        text = ambiguous_action_answer(part, compact=True)
                        child_paths.append("general_clarification")
                    elif classified.kind == "general_support":
                        text = general_support_answer(part, compact=True)
                        child_paths.append("general_clarification")
                    elif classified.kind == "needs_document_scope":
                        text = document_scope_clarification_answer(part, compact=True)
                        needs_document_scope_parts.append(part)
                        child_paths.append("document_scope_clarification")
                    elif classified.kind == "needs_scope":
                        text = scope_clarification_answer(part, compact=True)
                        needs_scope_parts.append(part)
                        child_paths.append("clarification")
                    else:
                        child = await self.query(
                            part,
                            rf,
                            top_k,
                            allowed_doc_ids,
                            # Each numbered section answers its own sub-question;
                            # the parent's full-question synthesis target would
                            # make every child refuse the other parts' topics.
                            synthesis_question=part,
                            # No conversation history for children: the split
                            # already yields standalone questions, and history
                            # makes a weak generator answer the PREVIOUS turn
                            # ("วิธีรีเซ็ต alarm...") instead of this part.
                            chat_history=None,
                            tuning=tuning,
                            allow_scope_broadening=allow_scope_broadening,
                            session_id=session_id,
                            question_raw=part,
                            rewrite_meta={**(rewrite_meta or {}), "compound_child": True},
                            session_slots=session_slots,
                            follow_up=follow_up,
                            last_retrieved_chunk_ids=last_retrieved_chunk_ids,
                        )
                        text = child.answer
                        sources.extend(child.sources or [])
                        top_doc_score = max(top_doc_score, float(child.top_doc_score or 0.0))
                        fallback_level = max(fallback_level, int(child.fallback_level or 0))
                        child_paths.append(child.answer_path)
                    answers.append(f"{idx}. **{part}**\n{text}")

                # De-duplicate source blocks by chunk/doc identity while preserving order.
                deduped_sources: list[dict[str, Any]] = []
                seen_sources: set[tuple[Any, Any]] = set()
                for source in sources:
                    key = (source.get("doc_id"), source.get("chunk_id"))
                    if key in seen_sources:
                        continue
                    seen_sources.add(key)
                    deduped_sources.append(source)

                guidance: list[str] = []
                if needs_document_scope_parts:
                    listed = "\n".join(f"- {p}" for p in needs_document_scope_parts)
                    guidance.append(
                        "## เอกสารที่ต้องการใช้\n"
                        "ช่วยเลือกไฟล์ในแชต หรือระบุชื่อไฟล์ รหัสเอกสาร ประเภทเอกสาร "
                        "หรือขอบเขตเอกสารสำหรับประเด็นเหล่านี้:\n"
                        f"{listed}"
                    )
                if needs_scope_parts:
                    listed = "\n".join(f"- {p}" for p in needs_scope_parts)
                    guidance.append(
                        "## เพื่อให้ค้นต่อได้แม่นขึ้น\n"
                        "ช่วยระบุรหัสเครื่องจักร รุ่นเครื่อง รหัสเอกสาร หรือเลข drawing/manual "
                        "สำหรับประเด็นเหล่านี้:\n"
                        f"{listed}"
                    )
                if external_parts:
                    guidance.append(
                        "## ข้อมูลสด\n"
                        "ถ้าต้องการให้ Neo วิเคราะห์ข้อมูลสดเหล่านี้ ให้อัปโหลดไฟล์หรือเอกสารที่มีข้อมูลนั้นก่อนครับ"
                    )
                answer_text = (
                    "## คำตอบแยกตามประเด็น\n"
                    "ผมแยกคำถามให้แล้ว เพื่อไม่ให้ประเด็นที่ตอบจากเอกสารได้ปนกับข้อมูลสดหรือคำถามที่ยังขาดขอบเขตครับ\n\n"
                    + "\n\n".join(answers)
                )
                if guidance:
                    answer_text += "\n\n" + "\n\n".join(guidance)

                return RAGResult(
                    answer=answer_text,
                    sources=deduped_sources,
                    used_filters={
                        "answer_path": "compound_answer",
                        "subquestions": parts,
                        "child_answer_paths": child_paths,
                    },
                    fallback_level=fallback_level,
                    intent="compound",
                    top_doc_score=top_doc_score,
                    answer_path="compound_answer",
                    retrieval_sources=[],
                )

        if is_external_live_question(question):
            return RAGResult(
                answer=external_live_answer(question),
                sources=[],
                used_filters={"answer_path": "external_live_unsupported"},
                fallback_level=0,
                intent="external_live",
                top_doc_score=0.0,
                answer_path="external_live_unsupported",
                retrieval_sources=[],
            )

        # Classify what the USER asked, not the rewritten retrieval form: the
        # follow-up rewrite legitimately pulls manual terminology into the query
        # ("แล้ว alarm นี้รีเซ็ตยังไง" → "วิธีรีเซ็ต Alarm 26h Motor overheat …"),
        # and words like "overheat" quoted from an alarm NAME must not trip the
        # symptom/emergency intercepts meant for user-reported hazards.
        classified_single = classify_subquestion(
            question_raw or question,
            machine_id=rf.machine_id,
            known_machine_ids=known_machine_ids,
        )
        if classified_single.kind == "sensitive":
            return RAGResult(
                answer=sensitive_request_answer(question),
                sources=[],
                used_filters={"answer_path": "sensitive_refusal"},
                fallback_level=0,
                intent="policy",
                top_doc_score=0.0,
                answer_path="sensitive_refusal",
                retrieval_sources=[],
            )
        if classified_single.kind == "safety_emergency":
            return RAGResult(
                answer=safety_emergency_answer(question),
                sources=[],
                used_filters={"answer_path": "safety_emergency"},
                fallback_level=0,
                intent="clarification",
                top_doc_score=0.0,
                answer_path="safety_emergency",
                retrieval_sources=[],
                clarification_suggested=True,
            )
        if classified_single.kind == "safety_procedure":
            return RAGResult(
                answer=safety_procedure_answer(question),
                sources=[],
                used_filters={"answer_path": "safety_procedure"},
                fallback_level=0,
                intent="clarification",
                top_doc_score=0.0,
                answer_path="safety_procedure",
                retrieval_sources=[],
                clarification_suggested=True,
            )
        if classified_single.kind == "factory_operation":
            return RAGResult(
                answer=factory_operation_answer(question),
                sources=[],
                used_filters={"answer_path": "factory_operation_clarification"},
                fallback_level=0,
                intent="clarification",
                top_doc_score=0.0,
                answer_path="factory_operation_clarification",
                retrieval_sources=[],
                clarification_suggested=True,
            )
        if classified_single.kind == "machine_context":
            return RAGResult(
                answer=machine_context_answer(question),
                sources=[],
                used_filters={"answer_path": "machine_context_clarification"},
                fallback_level=0,
                intent="clarification",
                top_doc_score=0.0,
                answer_path="machine_context_clarification",
                retrieval_sources=[],
                clarification_suggested=True,
            )
        if classified_single.kind == "out_of_scope":
            return RAGResult(
                answer=out_of_scope_answer(question),
                sources=[],
                used_filters={"answer_path": "out_of_scope"},
                fallback_level=0,
                intent="clarification",
                top_doc_score=0.0,
                answer_path="out_of_scope",
                retrieval_sources=[],
                clarification_suggested=True,
            )
        if classified_single.kind == "ambiguous_action":
            return RAGResult(
                answer=ambiguous_action_answer(question),
                sources=[],
                used_filters={"answer_path": "general_clarification", "reason": "ambiguous_action"},
                fallback_level=0,
                intent="clarification",
                top_doc_score=0.0,
                answer_path="general_clarification",
                retrieval_sources=[],
                clarification_suggested=True,
            )
        if classified_single.kind == "general_support":
            return RAGResult(
                answer=general_support_answer(question),
                sources=[],
                used_filters={"answer_path": "general_clarification"},
                fallback_level=0,
                intent="clarification",
                top_doc_score=0.0,
                answer_path="general_clarification",
                retrieval_sources=[],
                clarification_suggested=True,
            )
        if classified_single.kind == "needs_document_scope":
            return RAGResult(
                answer=document_scope_clarification_answer(question),
                sources=[],
                used_filters={"answer_path": "document_scope_clarification", "reason": "missing_document_scope"},
                fallback_level=0,
                intent="clarification",
                top_doc_score=0.0,
                answer_path="document_scope_clarification",
                retrieval_sources=[],
                clarification_suggested=True,
            )
        if classified_single.kind == "needs_scope":
            return RAGResult(
                answer=scope_clarification_answer(question),
                sources=[],
                used_filters={"answer_path": "clarification", "reason": "missing_scope"},
                fallback_level=0,
                intent="clarification",
                top_doc_score=0.0,
                answer_path="clarification",
                retrieval_sources=[],
                clarification_suggested=True,
            )

        inp = self._build_kernel_input(
            question,
            rf,
            top_k,
            allowed_doc_ids,
            synthesis_question=synthesis_question,
            chat_history=chat_history,
            tuning=tuning,
            allow_scope_broadening=allow_scope_broadening,
            session_id=session_id,
            question_raw=question_raw,
            rewrite_meta=rewrite_meta,
            session_slots=session_slots,
            follow_up=follow_up,
            last_retrieved_chunk_ids=last_retrieved_chunk_ids,
            stream=False,
            deadline_started_at=time.perf_counter(),
        )
        async for item in get_rag_kernel().run(inp, executor=self):
            if isinstance(item, RAGKernelOutput):
                result = item.result
                if item.degradation is not None:
                    deg = (
                        item.degradation.to_dict()
                        if hasattr(item.degradation, "to_dict")
                        else item.degradation
                    )
                    result = replace(result, system_degradation=deg)
                elif result.system_degradation is None:
                    result = replace(
                        result, system_degradation=self._build_system_degradation()
                    )
                return result
        raise RuntimeError("RAG kernel did not produce a result")

    async def _run_query_sync(
        self,
        question: str,
        rf: RAGFilter | None = None,
        top_k: int = 6,
        allowed_doc_ids: list[str] | None = None,
        *,
        synthesis_question: str | None = None,
        chat_history: list[tuple[str, str]] | None = None,
        tuning: RagTuningContext | None = None,
        allow_scope_broadening: bool = False,
        session_id: str | None = None,
        question_raw: str | None = None,
        rewrite_meta: dict[str, Any] | None = None,
        session_slots: dict[str, Any] | None = None,
        follow_up: bool = False,
        last_retrieved_chunk_ids: list[str] | None = None,
    ) -> RAGResult:
        import time as _time

        _start = _time.perf_counter()
        circuit_enabled = await self._rag_circuit_enabled(rf)
        circuit = await resolve_rag_circuit_decision(
            enabled=circuit_enabled,
            factory_id=(rf.factory_id if rf else None),
        )
        was_probe = circuit.mode == RAGCircuitMode.HALF_OPEN
        circuit_mode = circuit.mode.value
        try:
            result = await self._query_impl(
                question,
                rf,
                top_k,
                _start,
                allowed_doc_ids,
                synthesis_question=synthesis_question,
                chat_history=chat_history,
                tuning=tuning,
                allow_scope_broadening=allow_scope_broadening,
                session_id=session_id,
                skip_llm=circuit.skip_llm,
                force_rerank_degraded=circuit.force_rerank_degraded,
                circuit_enabled=circuit_enabled,
                question_raw=question_raw,
                rewrite_meta=rewrite_meta,
                session_slots=session_slots,
                follow_up=follow_up,
                last_retrieved_chunk_ids=last_retrieved_chunk_ids,
            )
            await record_rag_outcome_async(
                "success",
                enabled=circuit_enabled,
                factory_id=rf.factory_id if rf else None,
                was_half_open_probe=was_probe,
            )
            from spark.eval.embed_shadow import schedule_shadow_comparison
            schedule_shadow_comparison(
                query=question,
                factory_id=rf.factory_id if rf else None,
                production_results=result.sources or [],
                production_latency_ms=round((time.perf_counter() - _start) * 1000, 2),
            )
            return result
        except Exception as exc:
            log.error("rag_query_failed", error=str(exc)[:500], exc_info=True)
            await record_rag_outcome_async(
                "unhandled",
                enabled=circuit_enabled,
                factory_id=rf.factory_id if rf else None,
            )
            log.info(
                "rag_answer_produced",
                **rag_answer_produced_fields(
                    answer_path="service_unavailable",
                    retrieval_sources=[],
                    fallback_level=0,
                    top_doc_score=0.0,
                    sources_count=0,
                    latency_ms=round((time.perf_counter() - _start) * 1000, 2),
                    question=question,
                    circuit_mode=circuit_mode,
                ),
            )
            return RAGResult(
                answer=UNAVAILABLE_ANSWER,
                sources=[],
                used_filters={
                    "answer_path": "service_unavailable",
                    "retrieval_sources": [],
                },
                fallback_level=0,
                intent="factual",
                answer_path="service_unavailable",
                retrieval_sources=[],
            )

    async def _resolve_retrieval(
        self,
        question: str,
        rf: RAGFilter | None,
        top_k: int,
        _start: float,
        allowed_doc_ids: list[str] | None = None,
        *,
        tuning: RagTuningContext | None = None,
        allow_scope_broadening: bool = False,
        session_id: str | None = None,
        known_factory_machines: set[str] | None = None,
        circuit_enabled: bool = False,
        follow_up: bool = False,
        last_retrieved_chunk_ids: list[str] | None = None,
        deadline: RequestDeadline | None = None,
        session_slots: dict[str, Any] | None = None,
    ) -> _RetrievalBundle | _EarlyRAGResult:
        rf = rf or RAGFilter()
        deadline = deadline or RequestDeadline.from_settings(started_at=_start)
        from spark.services.session_slots import SessionSlots

        evidence_age_turns = SessionSlots.evidence_age_from_context(session_slots)
        intent_plan = IntentRouter().route(question)
        safety_intent = detect_safety_intent(question)
        effective_broadening = allow_scope_broadening
        if intent_plan.intent == QueryIntent.UNKNOWN and (
            features.has_loto_terms(question) or safety_intent.kind != SafetyIntentKind.NONE
        ):
            effective_broadening = False
        used_filters = {k: v for k, v in asdict(rf).items() if v not in (None, False)}
        scope_rf = rf
        fallback_ctx = FallbackContext(
            question=question,
            rf=rf,
            allow_scope_broadening=effective_broadening,
            safety_intent=safety_intent,
        )
        safety_label = safety_intent.kind.value

        def _used_with_path(
            *,
            answer_path: str,
            retrieval_sources: list[str],
        ) -> dict[str, Any]:
            return {
                **used_filters,
                "answer_path": answer_path,
                "retrieval_sources": retrieval_sources,
            }

        def _log_answer(
            *,
            answer_path: str,
            retrieval_sources: list[str],
            fallback_level: int,
            top_doc_score: float,
            sources_count: int,
            docs: list[RetrievedDoc] | None = None,
        ) -> None:
            log.info(
                "rag_answer_produced",
                **rag_answer_produced_fields(
                    answer_path=answer_path,
                    retrieval_sources=retrieval_sources,
                    fallback_level=fallback_level,
                    top_doc_score=top_doc_score,
                    sources_count=sources_count,
                    latency_ms=round((time.perf_counter() - _start) * 1000, 2),
                    question=question,
                    safety_intent=safety_label,
                    docs=docs,
                ),
            )

        def _early_no_data(reason: str) -> _EarlyRAGResult:
            log.info("rag_query_refused", reason=reason, question=question[:120])
            from spark.audit.worm_sink import schedule_worm_audit

            schedule_worm_audit(
                "safety_query_refused",
                factory_id=rf.factory_id,
                payload={
                    "reason": reason,
                    "question": question[:400],
                    "safety_intent": safety_label,
                },
            )
            _log_answer(
                answer_path="no_data",
                retrieval_sources=[],
                fallback_level=0,
                top_doc_score=0.0,
                sources_count=0,
            )
            refusal_answer = NO_DATA_ANSWER
            if reason == "unknown_machine" and rf.machine_id:
                from spark.retrieval.no_data import unknown_machine_answer

                refusal_answer = unknown_machine_answer(rf.machine_id)
            elif reason == "filter_machine_mismatch" and rf.machine_id:
                from spark.retrieval.no_data import machine_filter_mismatch_answer

                refusal_answer = machine_filter_mismatch_answer(question, rf.machine_id)
            return _EarlyRAGResult(
                result=RAGResult(
                    answer=refusal_answer,
                    sources=[],
                    used_filters=_used_with_path(
                        answer_path="no_data",
                        retrieval_sources=[],
                    ),
                    fallback_level=0,
                    intent="factual",
                    top_doc_score=0.0,
                    answer_path="no_data",
                    retrieval_sources=[],
                ),
            )

        pre_retrieval_refusal = should_refuse_rag_answer(
            question,
            rf,
            [],
            known_factory_machines=known_factory_machines,
        )
        if pre_retrieval_refusal:
            return _early_no_data(pre_retrieval_refusal)

        async def _retrieve_scoped(active_filter: RAGFilter) -> list[RetrievedDoc]:
            retrieved = await self._retrieve(
                question,
                active_filter,
                top_k,
                allowed_doc_ids,
                session_id=session_id,
                follow_up=follow_up,
                last_retrieved_chunk_ids=last_retrieved_chunk_ids,
                deadline=deadline,
                evidence_age_turns=evidence_age_turns,
            )
            return _filter_machine_conflicts(
                question,
                scope_rf,
                retrieved,
                known_factory_machines=known_factory_machines,
            )

        def _candidate_docs_ok(candidates: list[RetrievedDoc]) -> bool:
            return self._passes_relevance(
                candidates,
                question=question,
                tuning=tuning,
                intent_plan=intent_plan,
                circuit_enabled=circuit_enabled,
                factory_id=rf.factory_id,
            ) and _has_sufficient_evidence(
                question, scope_rf, candidates
            )

        docs, fallback_level, active_rf = await run_fallback_ladder(
            fallback_ctx,
            retrieve=_retrieve_scoped,
            candidate_ok=_candidate_docs_ok,
            latest_revision_only=bool(rf.latest_revision_only) and not rf.revision,
            filter_latest=self._filter_latest_revision,
            rerank_degraded=self._last_rerank_degraded,
            rerank_policy=self._last_rerank_policy,
        )
        from spark.retrieval.safety.fallback_audit import persist_scope_broadening_audit

        await persist_scope_broadening_audit(
            question=question,
            fallback_level=fallback_level,
            original_rf=rf,
            active_rf=active_rf,
            allow_scope_broadening=allow_scope_broadening,
        )
        if rf.revision:
            docs = self._filter_exact_revision(docs, rf.revision)

        report = self._last_retrieval_report or {}
        if requires_strict_retrieval(safety_intent) and "embed_failed" in (
            report.get("degraded_reasons") or []
        ):
            retrieval_sources = _retrieval_sources_from_docs(docs)
            self._observe_query_metrics(fallback_level=fallback_level, started_at=_start)
            _log_answer(
                answer_path="no_data",
                retrieval_sources=retrieval_sources,
                fallback_level=fallback_level,
                top_doc_score=0.0,
                sources_count=0,
                docs=docs,
            )
            return _EarlyRAGResult(
                result=RAGResult(
                    answer=NO_DATA_ANSWER,
                    sources=[],
                    used_filters=_used_with_path(
                        answer_path="no_data", retrieval_sources=retrieval_sources
                    ),
                    fallback_level=fallback_level,
                    intent="factual",
                    top_doc_score=0.0,
                    answer_path="no_data",
                    retrieval_sources=retrieval_sources,
                    retrieval_report=report,
                    system_degradation=self._build_system_degradation(fail_closed=True),
                ),
                docs=docs,
            )

        if requires_strict_retrieval(safety_intent) and fallback_level > 0:
            retrieval_sources = _retrieval_sources_from_docs(docs)
            self._observe_query_metrics(fallback_level=fallback_level, started_at=_start)
            _log_answer(
                answer_path="no_data",
                retrieval_sources=retrieval_sources,
                fallback_level=fallback_level,
                top_doc_score=0.0,
                sources_count=0,
                docs=docs,
            )
            return _EarlyRAGResult(
                result=RAGResult(
                    answer=NO_DATA_ANSWER,
                    sources=[],
                    used_filters=_used_with_path(
                        answer_path="no_data", retrieval_sources=retrieval_sources
                    ),
                    fallback_level=fallback_level,
                    intent="factual",
                    top_doc_score=0.0,
                    answer_path="no_data",
                    retrieval_sources=retrieval_sources,
                ),
                docs=docs,
            )

        from spark.retrieval.degraded_types import DegradedRetrievalPolicy

        if (
            self._last_rerank_degraded
            and requires_strict_retrieval(safety_intent)
            and self._last_rerank_policy == DegradedRetrievalPolicy.CE_TIMEOUT_ABSTAIN.value
        ):
            retrieval_sources = _retrieval_sources_from_docs(docs)
            self._observe_query_metrics(fallback_level=fallback_level, started_at=_start)
            _log_answer(
                answer_path="rerank_degraded_abstain",
                retrieval_sources=retrieval_sources,
                fallback_level=fallback_level,
                top_doc_score=0.0,
                sources_count=0,
                docs=docs,
            )
            return _EarlyRAGResult(
                result=RAGResult(
                    answer=NO_DATA_ANSWER,
                    sources=[],
                    used_filters=_used_with_path(
                        answer_path="rerank_degraded_abstain",
                        retrieval_sources=retrieval_sources,
                    ),
                    fallback_level=fallback_level,
                    intent="factual",
                    top_doc_score=0.0,
                    answer_path="rerank_degraded_abstain",
                    retrieval_sources=retrieval_sources,
                    retrieval_report=report,
                    system_degradation=self._build_system_degradation(fail_closed=True),
                ),
                docs=docs,
            )

        if not docs or not _candidate_docs_ok(docs):
            # Weak-evidence continuation: the lexical evidence heuristics are
            # structurally unreliable for cross-lingual (Thai question over an
            # English manual) and paraphrased questions. When retrieval DID find
            # candidates and the question is not safety-critical, let generation
            # try — its own citation/self-verify gates still decide whether the
            # answer is shown verified, flagged unverified, or suppressed.
            weak_floor = float(getattr(settings, "rag_weak_evidence_min_score", 0.15))
            best_score = max((float(d.score) for d in docs), default=0.0)
            weak_continue = (
                bool(docs)
                and safety_intent.kind == SafetyIntentKind.NONE
                and best_score >= weak_floor
            )
            if weak_continue:
                log.info(
                    "rag_weak_evidence_continue",
                    best_score=round(best_score, 4),
                    candidates=len(docs),
                    fallback_level=fallback_level,
                )
                used_filters = {**used_filters, "evidence_weak": True}
            else:
                from spark.retrieval.no_data import build_no_data_answer

                retrieval_sources = _retrieval_sources_from_docs(docs)
                self._observe_query_metrics(fallback_level=fallback_level, started_at=_start)
                _log_answer(
                    answer_path="no_data",
                    retrieval_sources=retrieval_sources,
                    fallback_level=fallback_level,
                    top_doc_score=0.0,
                    sources_count=0,
                    docs=docs,
                )
                return _EarlyRAGResult(
                    result=RAGResult(
                        answer=build_no_data_answer(
                            question,
                            docs,
                            rf=scope_rf,
                            is_safety=safety_intent.kind != SafetyIntentKind.NONE,
                        ),
                        sources=[],
                        used_filters=_used_with_path(
                            answer_path="no_data", retrieval_sources=retrieval_sources
                        ),
                        fallback_level=fallback_level,
                        intent="factual",
                        top_doc_score=0.0,
                        answer_path="no_data",
                        retrieval_sources=retrieval_sources,
                    ),
                    docs=docs,
                )

        top_doc_score = max((d.score for d in docs), default=0.0)
        post_retrieval_refusal = should_refuse_rag_answer(
            question,
            rf,
            docs,
            known_factory_machines=known_factory_machines,
        )
        if post_retrieval_refusal:
            return _early_no_data(post_retrieval_refusal)

        return _RetrievalBundle(
            docs=docs,
            fallback_level=fallback_level,
            used_filters=used_filters,
            top_doc_score=top_doc_score,
            scope_rf=scope_rf,
            retrieval_report=self._last_retrieval_report,
            clarification_suggested=intent_plan.clarification_suggested,
        )

    async def _query_impl(
        self,
        question: str,
        rf: RAGFilter | None,
        top_k: int,
        _start: float,
        allowed_doc_ids: list[str] | None = None,
        *,
        synthesis_question: str | None = None,
        chat_history: list[tuple[str, str]] | None = None,
        tuning: RagTuningContext | None = None,
        allow_scope_broadening: bool = False,
        session_id: str | None = None,
        skip_llm: bool = False,
        force_rerank_degraded: bool = False,
        circuit_enabled: bool = False,
        safety_intent_kind: str = "none",
        circuit_mode: str = "closed",
        question_raw: str | None = None,
        rewrite_meta: dict[str, Any] | None = None,
        session_slots: dict[str, Any] | None = None,
        follow_up: bool = False,
        last_retrieved_chunk_ids: list[str] | None = None,
        deadline: RequestDeadline | None = None,
    ) -> RAGResult:
        rf = rf or RAGFilter()
        deadline = deadline or RequestDeadline.from_settings(started_at=_start)
        _start = deadline.started_at
        self._last_rerank_degraded = False
        self._last_rerank_policy = "ce_active"
        self._force_degraded_no_llm = False
        self._force_rerank_circuit_degraded = force_rerank_degraded
        fusion_method = tuning.fusion_method if tuning else "rrf"
        safety_intent = detect_safety_intent(question)
        safety_label = safety_intent_kind or safety_intent.kind.value

        def _attach_snapshot(
            result: RAGResult,
            docs: list[RetrievedDoc],
            *,
            retrieval_report: dict[str, Any] | None = None,
            fail_closed: bool = False,
        ) -> RAGResult:
            if result.retrieval_snapshot is not None and result.retrieval_report is not None:
                if result.system_degradation is None:
                    return replace(
                        result,
                        system_degradation=self._build_system_degradation(fail_closed=fail_closed),
                    )
                return result
            snapshot = result.retrieval_snapshot
            if snapshot is None:
                snapshot = build_retrieval_snapshot(
                    question_raw=question_raw,
                    question_retrieval=question,
                    question_synthesis=synthesis_question or question,
                    fallback_level=result.fallback_level,
                    docs=docs,
                    fusion_method=fusion_method,
                    rewrite_meta=rewrite_meta,
                    intent=(retrieval_report or {}).get("intent"),
                    session_slots=session_slots,
                    retrieval_report=retrieval_report or self._last_retrieval_report,
                    intent_plan=self._intent_plan_snapshot(
                        self.retrieval_engine.last_intent_plan
                    ),
                    intent_weight_version=(
                        self.retrieval_engine.last_intent_plan.weight_version
                        if self.retrieval_engine.last_intent_plan
                        else None
                    ),
                )
            llm_usage = (result.used_filters or {}).get("llm_usage")
            if llm_usage and isinstance(snapshot, dict):
                snapshot = {**snapshot, "llm_usage": llm_usage}
            report = retrieval_report if retrieval_report is not None else result.retrieval_report
            degradation = result.system_degradation
            if degradation is None and result.answer_path == "system_degraded":
                from spark.contracts.degradation_contract import circuit_open_degradation

                degradation = circuit_open_degradation(fail_closed=fail_closed).to_dict()
            elif degradation is None:
                degradation = self._build_system_degradation(fail_closed=fail_closed)
            return replace(
                result,
                retrieval_snapshot=snapshot,
                retrieval_report=report,
                system_degradation=degradation,
            )

        known_machines = await _load_factory_machine_ids(rf.factory_id)
        resolved = await self._resolve_retrieval(
            question,
            rf,
            top_k,
            _start,
            allowed_doc_ids,
            tuning=tuning,
            allow_scope_broadening=allow_scope_broadening,
            session_id=session_id,
            known_factory_machines=known_machines,
            circuit_enabled=circuit_enabled,
            follow_up=follow_up,
            last_retrieved_chunk_ids=last_retrieved_chunk_ids,
            deadline=deadline,
            session_slots=session_slots,
        )
        if isinstance(resolved, _EarlyRAGResult):
            fail_closed = bool(
                (resolved.result.system_degradation or {}).get("fail_closed")
            )
            return _attach_snapshot(
                resolved.result,
                resolved.docs,
                retrieval_report=self._last_retrieval_report,
                fail_closed=fail_closed,
            )

        docs = resolved.docs
        fallback_level = resolved.fallback_level
        used_filters = resolved.used_filters
        top_doc_score = resolved.top_doc_score
        retrieval_report = resolved.retrieval_report
        clarification_suggested = resolved.clarification_suggested

        def _used_with_path(
            *,
            answer_path: str,
            retrieval_sources: list[str],
        ) -> dict[str, Any]:
            used = {
                **used_filters,
                "answer_path": answer_path,
                "retrieval_sources": retrieval_sources,
            }
            if getattr(gen, "llm_usage", None):
                used["llm_usage"] = gen.llm_usage
            return used

        def _log_answer(
            *,
            answer_path: str,
            retrieval_sources: list[str],
            fallback_level: int,
            top_doc_score: float,
            sources_count: int,
            docs: list[RetrievedDoc] | None = None,
        ) -> None:
            log.info(
                "rag_answer_produced",
                **rag_answer_produced_fields(
                    answer_path=answer_path,
                    retrieval_sources=retrieval_sources,
                    fallback_level=fallback_level,
                    top_doc_score=top_doc_score,
                    sources_count=sources_count,
                    latency_ms=round((time.perf_counter() - _start) * 1000, 2),
                    question=question,
                    safety_intent=safety_label,
                    circuit_mode=circuit_mode,
                    docs=docs,
                ),
            )

        ordered_docs = _order_docs_for_context(question, docs)
        budget = build_rag_context_budget(question)
        trim_result = fit_docs_to_budget(ordered_docs, budget.doc_budget_tokens)
        if trim_result.trimmed_chunks > 0:
            context_trim_total.labels(trim_result.reason).inc()
            log_context_budget_applied(question=question, budget=budget, trim=trim_result)
        ordered_docs = trim_result.docs

        if skip_llm or self._force_degraded_no_llm:
            gen = await _generate_under_circuit_open(question, ordered_docs)
        else:
            policy = await resolve_generation_policy(rf)
            # A standalone question gains nothing from prior turns — the
            # evidence is already selected — but the gateway model has been
            # observed answering the PREVIOUS turn instead of the current one
            # when history is present (same failure the compound children fix
            # addressed). Only genuine follow-ups need history to resolve
            # deixis, so everything else generates history-free.
            gen = await grounded_generate_with_enforced_citations(
                question=question,
                docs=ordered_docs,
                llm=self._get_llm(),
                chat_history=chat_history if follow_up else None,
                synthesis_question=synthesis_question,
                policy=policy,
                deadline=deadline,
            )

        gen = await self._humanize_no_data(
            question, gen, ordered_docs, rf, chat_history=chat_history
        )
        answer = gen.answer
        answer_path = gen.answer_path

        if gen.citations_verified and gen.cited_docs:
            display_docs = gen.cited_docs
        elif answer_path in ("no_data", "llm_unavailable", "rag_circuit_open", "system_degraded"):
            display_docs = []
        elif answer_path == "grounded_unverified" and gen.cited_docs:
            # Flagged-but-shown text still cites specific chunks — source cards
            # must mirror those, not a similarity re-pick over the whole
            # retrieval set (which cards the answer with documents it never used).
            display_docs = gen.cited_docs
        else:
            display_docs = _select_sources_for_display(ordered_docs, answer, question=question)

        sources = cited_docs_to_sources(question, display_docs) if (
            gen.citations_verified and gen.cited_docs
        ) else [_payload_to_source(d.payload, d) for d in display_docs]
        retrieval_sources = _retrieval_sources_from_docs(ordered_docs)
        self._observe_query_metrics(fallback_level=fallback_level, started_at=_start)
        rag_fallback_level_histogram.observe(float(fallback_level))
        _log_answer(
            answer_path=answer_path,
            retrieval_sources=retrieval_sources,
            fallback_level=fallback_level,
            top_doc_score=top_doc_score,
            sources_count=len(sources),
            docs=ordered_docs,
        )
        return _attach_snapshot(
            RAGResult(
                answer=answer,
                sources=sources,
                used_filters=_used_with_path(
                    answer_path=answer_path,
                    retrieval_sources=retrieval_sources,
                ),
                fallback_level=fallback_level,
                intent="factual",
                top_doc_score=top_doc_score,
                answer_path=answer_path,
                retrieval_sources=retrieval_sources,
                clarification_suggested=clarification_suggested,
            ),
            ordered_docs,
            retrieval_report=retrieval_report,
        )

    async def query_stream(
        self,
        question: str,
        rf: RAGFilter | None = None,
        top_k: int = 6,
        allowed_doc_ids: list[str] | None = None,
        *,
        synthesis_question: str | None = None,
        chat_history: list[tuple[str, str]] | None = None,
        tuning: RagTuningContext | None = None,
        allow_scope_broadening: bool = False,
        session_id: str | None = None,
        question_raw: str | None = None,
        rewrite_meta: dict[str, Any] | None = None,
        session_slots: dict[str, Any] | None = None,
        follow_up: bool = False,
        last_retrieved_chunk_ids: list[str] | None = None,
        cancel_event: Any | None = None,
    ) -> AsyncIterator[str | RAGResult | RAGStreamPhaseMeta]:
        """Yield token deltas then final RAGResult via RAGKernel."""
        from spark.retrieval.preprocess.adaptive import classify_retrieval_need
        from spark.retrieval.preprocess.compound import (
            classify_subquestion,
            is_external_live_question,
            is_policy_question,
            is_sensitive_request,
            split_compound_question,
        )

        rf = rf or RAGFilter()
        known_machine_ids = await _load_factory_machine_ids(rf.factory_id)
        adaptive = classify_retrieval_need(question)
        classified = classify_subquestion(
            question, machine_id=rf.machine_id, known_machine_ids=known_machine_ids
        )
        should_short_circuit = (
            adaptive.decision != "retrieve"
            or is_external_live_question(question)
            or is_policy_question(question)
            or is_sensitive_request(question)
            or len(split_compound_question(question)) >= 2
            or classified.kind in {
                "needs_scope",
                "needs_document_scope",
                "policy",
                "sensitive",
                "safety_emergency",
                "safety_procedure",
                "factory_operation",
                "machine_context",
                "out_of_scope",
                "ambiguous_action",
                "general_support",
            }
        )
        if should_short_circuit:
            result = await self.query(
                question,
                rf,
                top_k,
                allowed_doc_ids,
                synthesis_question=synthesis_question,
                chat_history=chat_history,
                tuning=tuning,
                allow_scope_broadening=allow_scope_broadening,
                session_id=session_id,
                question_raw=question_raw,
                rewrite_meta=rewrite_meta,
                session_slots=session_slots,
                follow_up=follow_up,
                last_retrieved_chunk_ids=last_retrieved_chunk_ids,
            )
            yield result.answer
            yield result
            return

        inp = self._build_kernel_input(
            question,
            rf,
            top_k,
            allowed_doc_ids,
            synthesis_question=synthesis_question,
            chat_history=chat_history,
            tuning=tuning,
            allow_scope_broadening=allow_scope_broadening,
            session_id=session_id,
            question_raw=question_raw,
            rewrite_meta=rewrite_meta,
            session_slots=session_slots,
            follow_up=follow_up,
            last_retrieved_chunk_ids=last_retrieved_chunk_ids,
            stream=True,
            deadline_started_at=time.perf_counter(),
            cancel_event=cancel_event,
        )
        async for item in get_rag_kernel().run(inp, executor=self):
            yield item

    async def _query_stream_impl(
        self,
        question: str,
        rf: RAGFilter | None,
        top_k: int,
        _start: float,
        allowed_doc_ids: list[str] | None,
        *,
        synthesis_question: str | None = None,
        chat_history: list[tuple[str, str]] | None = None,
        tuning: RagTuningContext | None = None,
        skip_llm: bool = False,
        force_rerank_degraded: bool = False,
        circuit_enabled: bool = False,
        safety_intent_kind: str = "none",
        circuit_mode: str = "closed",
        question_raw: str | None = None,
        rewrite_meta: dict[str, Any] | None = None,
        session_slots: dict[str, Any] | None = None,
        follow_up: bool = False,
        last_retrieved_chunk_ids: list[str] | None = None,
        allow_scope_broadening: bool = False,
        session_id: str | None = None,
        deadline: RequestDeadline | None = None,
        cancel_event: Any | None = None,
    ) -> AsyncIterator[str | RAGResult | RAGStreamPhaseMeta]:
        import asyncio

        from spark.retrieval.models import RAGStreamError, RAGStreamToken, RAGStreamCitationBlock

        def _check_cancel() -> None:
            if cancel_event is not None and cancel_event.is_set():
                raise asyncio.CancelledError("rag stream cancelled by client disconnect")

        rf = rf or RAGFilter()
        deadline = deadline or RequestDeadline.from_settings(started_at=_start)
        _start = deadline.started_at
        self._last_rerank_degraded = False
        self._last_rerank_policy = "ce_active"
        self._force_degraded_no_llm = False
        self._force_rerank_circuit_degraded = force_rerank_degraded
        fusion_method = tuning.fusion_method if tuning else "rrf"

        _check_cancel()
        yield RAGStreamPhaseMeta(
            retrieval_report={"phase": "searching"},
            system_degradation=None,
        )

        # Load the factory's machine registry so the cross-machine conflict
        # guard recognizes alpha-only machine IDs (MC-GOLDEN-KSS, PUMP-MAIN).
        # Without this the streaming path — the web UI default — leaves
        # _filter_machine_conflicts a no-op for non-numeric IDs, letting another
        # machine's manual answer the question. Mirrors _query_impl (non-stream).
        known_machines = await _load_factory_machine_ids(rf.factory_id)
        resolved = await self._resolve_retrieval(
            question,
            rf,
            top_k,
            _start,
            allowed_doc_ids,
            tuning=tuning,
            allow_scope_broadening=allow_scope_broadening,
            session_id=session_id,
            known_factory_machines=known_machines,
            circuit_enabled=circuit_enabled,
            follow_up=follow_up,
            last_retrieved_chunk_ids=last_retrieved_chunk_ids,
            deadline=deadline,
            session_slots=session_slots,
        )

        def _attach_snapshot(
            result: RAGResult,
            docs: list[RetrievedDoc],
            *,
            retrieval_report: dict[str, Any] | None = None,
            fail_closed: bool = False,
        ) -> RAGResult:
            if result.retrieval_snapshot is not None and result.retrieval_report is not None:
                if result.system_degradation is None:
                    return replace(
                        result,
                        system_degradation=self._build_system_degradation(fail_closed=fail_closed),
                    )
                return result
            snapshot = result.retrieval_snapshot
            if snapshot is None:
                snapshot = build_retrieval_snapshot(
                    question_raw=question_raw,
                    question_retrieval=question,
                    question_synthesis=synthesis_question or question,
                    fallback_level=result.fallback_level,
                    docs=docs,
                    fusion_method=fusion_method,
                    rewrite_meta=rewrite_meta,
                    intent=(retrieval_report or {}).get("intent"),
                    session_slots=session_slots,
                    retrieval_report=retrieval_report or self._last_retrieval_report,
                    intent_plan=self._intent_plan_snapshot(
                        self.retrieval_engine.last_intent_plan
                    ),
                    intent_weight_version=(
                        self.retrieval_engine.last_intent_plan.weight_version
                        if self.retrieval_engine.last_intent_plan
                        else None
                    ),
                )
            llm_usage = (result.used_filters or {}).get("llm_usage")
            if llm_usage and isinstance(snapshot, dict):
                snapshot = {**snapshot, "llm_usage": llm_usage}
            report = retrieval_report if retrieval_report is not None else result.retrieval_report
            degradation = result.system_degradation
            if degradation is None and result.answer_path == "system_degraded":
                from spark.contracts.degradation_contract import circuit_open_degradation

                degradation = circuit_open_degradation(fail_closed=fail_closed).to_dict()
            elif degradation is None:
                degradation = self._build_system_degradation(fail_closed=fail_closed)
            return replace(
                result,
                retrieval_snapshot=snapshot,
                retrieval_report=report,
                system_degradation=degradation,
            )

        if isinstance(resolved, _EarlyRAGResult):
            fail_closed = bool(
                (resolved.result.system_degradation or {}).get("fail_closed")
            )
            early = _attach_snapshot(
                resolved.result,
                resolved.docs,
                retrieval_report=self._last_retrieval_report,
                fail_closed=fail_closed,
            )
            yield RAGStreamPhaseMeta(
                retrieval_report=early.retrieval_report,
                system_degradation=early.system_degradation,
            )
            if early.answer:
                yield early.answer
            yield early
            return

        docs = resolved.docs
        fallback_level = resolved.fallback_level
        used_filters = resolved.used_filters
        top_doc_score = resolved.top_doc_score
        retrieval_report = resolved.retrieval_report

        ordered_docs = _order_docs_for_context(question, docs)
        budget = build_rag_context_budget(question)
        trim_result = fit_docs_to_budget(ordered_docs, budget.doc_budget_tokens)
        if trim_result.trimmed_chunks > 0:
            context_trim_total.labels(trim_result.reason).inc()
            log_context_budget_applied(question=question, budget=budget, trim=trim_result)
        ordered_docs = trim_result.docs

        yield RAGStreamPhaseMeta(
            retrieval_report=retrieval_report or self._last_retrieval_report,
            system_degradation=self._build_system_degradation(fail_closed=False),
        )

        if skip_llm or self._force_degraded_no_llm:
            gen = await _generate_under_circuit_open(question, ordered_docs)
            streamed_tokens = False
        else:
            from spark.generation.pipeline import build_generation_input
            from spark.generation.streaming import stream_grounded_answer

            policy = await resolve_generation_policy(rf)
            # History-free generation for standalone questions — mirrors the
            # sync path: the gateway model answers the previous turn instead
            # of the current one often enough that history is net harmful
            # unless the question actually needs it to resolve deixis.
            inp = build_generation_input(
                question=question,
                docs=ordered_docs,
                llm=self._get_llm(),
                chat_history=chat_history if follow_up else None,
                synthesis_question=synthesis_question,
                policy=policy,
                deadline=deadline,
            )
            inp.cancel_event = cancel_event
            gen = None
            streamed_tokens = False
            async for event in stream_grounded_answer(inp):
                _check_cancel()
                if event.kind == "token_provisional" and event.delta:
                    streamed_tokens = True
                    yield RAGStreamToken(event.delta, provisional=True)
                elif event.kind == "token" and event.delta:
                    streamed_tokens = True
                    yield RAGStreamToken(event.delta, provisional=False)
                elif event.kind == "citation_block" and event.result is not None:
                    gen = event.result
                    streamed_tokens = True
                    yield RAGStreamCitationBlock(
                        text=event.result.answer,
                        citations_verified=bool(event.result.citations_verified),
                    )
                elif event.kind == "error" and event.message:
                    log.warning("rag_generation_stream_error", message=event.message)
                    yield RAGStreamError(event.message, event.message)
                    return
                elif event.kind == "done" and event.result is not None:
                    gen = event.result
            if gen is None:
                from spark.generation.types import GroundedGenerateResult as _GenResult

                gen = _GenResult(
                    answer=NO_DATA_ANSWER,
                    cited_docs=[],
                    answer_path="no_data",
                    citations_verified=False,
                )

        streamed_answer = gen.answer if gen is not None else None
        gen = await self._humanize_no_data(
            question, gen, ordered_docs, rf, chat_history=chat_history
        )
        if not streamed_tokens:
            if gen.answer and gen.answer_path not in (
                "no_data",
                "llm_unavailable",
                "rag_circuit_open",
                "system_degraded",
            ):
                yield gen.answer
            elif gen.answer_path in (
                "no_data",
                "llm_unavailable",
                "rag_circuit_open",
                "system_degraded",
            ) and gen.answer:
                yield gen.answer
        elif gen.answer and gen.answer != streamed_answer:
            # Humanizing rewrote the answer after generation had already streamed
            # the terse version, and the client only swaps text on a citation
            # block. Without this resend the near-miss docs and search tips reach
            # storage but never the screen, so the live turn is the bare
            # "ไม่พบข้อมูล" the humanizer exists to replace.
            yield RAGStreamCitationBlock(text=gen.answer, citations_verified=False)
        result = self._package_grounded_result(
            question=question,
            gen=gen,
            ordered_docs=ordered_docs,
            fallback_level=fallback_level,
            top_doc_score=top_doc_score,
            used_filters=used_filters,
            _start=_start,
        )
        yield _attach_snapshot(result, ordered_docs, retrieval_report=retrieval_report)

    @staticmethod
    def _early_policy_block(question: str) -> RAGResult | None:
        """Fail-closed blocklist verdict, or None when the query is allowed."""
        from spark.contracts.degradation_contract import policy_block_degradation
        from spark.retrieval.safety.query_policy import scan_query

        policy = scan_query(question)
        if policy.action != "block":
            return None
        answer_path = policy.answer_path or "query_policy_block"
        return RAGResult(
            answer=NO_DATA_ANSWER,
            sources=[],
            used_filters={"answer_path": answer_path, "retrieval_sources": []},
            fallback_level=0,
            intent="factual",
            answer_path=answer_path,
            retrieval_sources=[],
            system_degradation=policy_block_degradation(fail_closed=True).to_dict(),
        )

    async def _humanize_no_data(
        self,
        question: str,
        gen: Any,
        docs: list[RetrievedDoc],
        rf: RAGFilter | None,
        *,
        chat_history: list[tuple[str, str]] | None = None,
    ) -> Any:
        """Return gen with refusal-style answers normalized to helpful no-data
        (gen is frozen — a new instance is returned when changed).

        Two shapes are normalized:
        1. Generation-time suppression returned the bare NO_DATA_ANSWER — the
           user-facing turn should instead say what WAS found and how to
           search better. Safety questions keep the terse fail-closed text.
        2. The LLM wrote a refusal ("ไม่พบข้อมูลในระบบ ...") but attached a
           citation, so it sailed through validation as a verified answer —
           pairing "ไม่พบข้อมูล" with source cards reads as a contradiction.
           Before declaring no-data, the deterministic extractive rescue gets
           one shot: a cited refusal means retrieval found *something*, and
           when the question is anchored (PLC tag / quoted manual terms) the
           evidence span usually IS the answer the weak generator refused to
           write.
        """
        if gen is None:
            return gen
        stripped = (gen.answer or "").strip()

        canned_no_data = gen.answer_path == "no_data" and stripped == NO_DATA_ANSWER
        cited_refusal = (
            gen.answer_path not in ("no_data",)
            and _is_pure_refusal_answer(stripped)
        )
        if not canned_no_data and not cited_refusal:
            return gen

        if cited_refusal:
            from spark.generation.unverified import _extractive_rescue

            rescued = await _extractive_rescue(
                question, docs, self._get_llm(), chat_history
            )
            if rescued is not None:
                log.info("cited_refusal_extractive_rescue", answer_path=gen.answer_path)
                return rescued

        from spark.retrieval.no_data import build_no_data_answer
        from spark.retrieval.safety.safety_intent import SafetyIntentKind, detect_safety_intent

        helpful = build_no_data_answer(
            question,
            docs,
            rf=rf,
            is_safety=detect_safety_intent(question).kind != SafetyIntentKind.NONE,
        )
        if cited_refusal:
            log.info("cited_refusal_normalized_to_no_data", answer_path=gen.answer_path)
            return replace(
                gen,
                answer=helpful,
                answer_path="no_data",
                citations_verified=False,
                cited_docs=[],
            )
        return replace(gen, answer=helpful)

    def _package_grounded_result(
        self,
        *,
        question: str,
        gen: Any,
        ordered_docs: list[RetrievedDoc],
        fallback_level: int,
        top_doc_score: float,
        used_filters: dict[str, Any],
        _start: float,
    ) -> RAGResult:
        def _used_with_path(
            *,
            answer_path: str,
            retrieval_sources: list[str],
        ) -> dict[str, Any]:
            used = {
                **used_filters,
                "answer_path": answer_path,
                "retrieval_sources": retrieval_sources,
            }
            if getattr(gen, "llm_usage", None):
                used["llm_usage"] = gen.llm_usage
            return used

        answer = gen.answer
        answer_path = gen.answer_path
        if gen.citations_verified and gen.cited_docs:
            display_docs = gen.cited_docs
        elif answer_path in (
            "no_data",
            "llm_unavailable",
            "rag_circuit_open",
            "system_degraded",
        ):
            display_docs = []
        elif answer_path == "grounded_unverified" and gen.cited_docs:
            # Flagged-but-shown text still cites specific chunks — source cards
            # must mirror those, not a similarity re-pick over the whole
            # retrieval set (which cards the answer with documents it never used).
            display_docs = gen.cited_docs
        else:
            display_docs = _select_sources_for_display(ordered_docs, answer, question=question)

        sources = (
            cited_docs_to_sources(question, display_docs)
            if gen.citations_verified and gen.cited_docs
            else [_payload_to_source(d.payload, d) for d in display_docs]
        )
        retrieval_sources = _retrieval_sources_from_docs(ordered_docs)
        self._observe_query_metrics(fallback_level=fallback_level, started_at=_start)
        log.info(
            "rag_answer_produced",
            **rag_answer_produced_fields(
                answer_path=answer_path,
                retrieval_sources=retrieval_sources,
                fallback_level=fallback_level,
                top_doc_score=top_doc_score,
                sources_count=len(sources),
                latency_ms=round((time.perf_counter() - _start) * 1000, 2),
                question=question,
                docs=ordered_docs,
            ),
        )
        return RAGResult(
            answer=answer,
            sources=sources,
            used_filters=_used_with_path(
                answer_path=answer_path, retrieval_sources=retrieval_sources
            ),
            fallback_level=fallback_level,
            intent=self._intent_label_for_metrics(),
            top_doc_score=top_doc_score,
            answer_path=answer_path,
            retrieval_sources=retrieval_sources,
            retrieval_report=self._last_retrieval_report,
        )

    def _package_rag_result(
        self,
        *,
        question: str,
        answer: str,
        ordered_docs: list[RetrievedDoc],
        context: str,
        synth_docs: list[RetrievedDoc] | None,
        fallback_level: int,
        top_doc_score: float,
        used_filters: dict[str, Any],
        answer_path: str,
        _start: float,
    ) -> RAGResult:
        """Legacy packaging hook for compat shims — delegates to grounded result shape."""
        from spark.generation.types import GroundedGenerateResult

        gen = GroundedGenerateResult(
            answer=answer,
            cited_docs=synth_docs or [],
            answer_path=answer_path,
            citations_verified=bool(synth_docs),
        )
        return self._package_grounded_result(
            question=question,
            gen=gen,
            ordered_docs=ordered_docs,
            fallback_level=fallback_level,
            top_doc_score=top_doc_score,
            used_filters=used_filters,
            _start=_start,
        )


rag_service = lazy_singleton(lambda: RAGService())
