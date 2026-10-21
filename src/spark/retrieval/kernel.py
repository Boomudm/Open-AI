"""Single RAG execution kernel — sync and stream share guardrails (Phase 9)."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any, AsyncIterator, Protocol

if TYPE_CHECKING:
    from spark.retrieval.models import RAGFilter, RAGResult
    from spark.retrieval.tuning import RagTuningContext


@dataclass(frozen=True)
class RAGEvent:
    """Structured audit event emitted during kernel execution."""

    name: str
    payload: dict[str, Any]


@dataclass
class RAGKernelInput:
    question: str
    rf: RAGFilter | None = None
    top_k: int = 6
    allowed_doc_ids: list[str] | None = None
    synthesis_question: str | None = None
    chat_history: list[tuple[str, str]] | None = None
    tuning: RagTuningContext | None = None
    allow_scope_broadening: bool = False
    session_id: str | None = None
    question_raw: str | None = None
    rewrite_meta: dict[str, Any] | None = None
    session_slots: dict[str, Any] | None = None
    follow_up: bool = False
    last_retrieved_chunk_ids: list[str] | None = None
    stream: bool = False
    skip_llm: bool = False
    force_rerank_degraded: bool = False
    embed_breaker_open: bool = False
    circuit_enabled: bool = False
    circuit_mode: str = "closed"
    safety_intent: str = "none"
    entry_degradation: Any = None
    deadline_started_at: float | None = None
    cancel_event: Any | None = None


@dataclass
class RAGKernelOutput:
    result: RAGResult
    events: list[RAGEvent] = field(default_factory=list)
    degradation: Any = None


class RAGKernelExecutor(Protocol):
    async def execute_sync(self, inp: RAGKernelInput) -> RAGKernelOutput: ...

    def execute_stream(self, inp: RAGKernelInput) -> AsyncIterator[str | RAGResult]: ...


class RAGKernel:
    """Orchestrates RAG sync/stream through one executor with safety guardrails."""

    async def _apply_entry_guardrails(self, inp: RAGKernelInput) -> RAGKernelInput | RAGKernelOutput:
        from spark.contracts.degradation_contract import (
            circuit_open_degradation,
            policy_block_degradation,
        )
        from spark.core.production_profile import ProductionProfile
        from spark.retrieval.circuit import resolve_circuit_decision
        from spark.retrieval.intent import features
        from spark.retrieval.intent.router import IntentRouter, QueryIntent
        from spark.retrieval.safety.query_policy import scan_query
        from spark.retrieval.safety.safety_intent import detect_safety_intent, requires_strict_retrieval
        from spark.retrieval.constants import NO_DATA_ANSWER
        from spark.retrieval.models import RAGResult

        policy = scan_query(inp.question)
        if policy.action == "block":
            result = RAGResult(
                answer=NO_DATA_ANSWER,
                sources=[],
                used_filters={
                    "answer_path": policy.answer_path or "query_policy_block",
                    "retrieval_sources": [],
                },
                fallback_level=0,
                intent="factual",
                answer_path=policy.answer_path or "query_policy_block",
                retrieval_sources=[],
            )
            return RAGKernelOutput(
                result=result,
                events=[RAGEvent("query_policy_block", {"reason": policy.reason})],
                degradation=policy_block_degradation(fail_closed=True),
            )

        safety = detect_safety_intent(inp.question)
        rf = inp.rf
        circuit_enabled = ProductionProfile.from_settings().rag_circuit_enabled
        if rf and rf.factory_id:
            from spark.core.database import AsyncSessionLocal
            from spark.services.factory_config_service import factory_config_service

            async with AsyncSessionLocal() as session:
                factory_cfg = await factory_config_service.resolve(session, rf.factory_id)
            circuit_enabled = ProductionProfile.for_factory(factory_cfg).rag_circuit_enabled

        circuit = await resolve_circuit_decision(
            enabled=circuit_enabled,
            factory_id=(rf.factory_id if rf else None),
        )

        intent_plan = IntentRouter().route(inp.question)
        allow_broadening = inp.allow_scope_broadening
        if intent_plan.intent == QueryIntent.UNKNOWN and (
            features.has_loto_terms(inp.question) or safety.kind.value != "none"
        ):
            allow_broadening = False

        if circuit.embed_breaker_open and requires_strict_retrieval(safety):
            result = RAGResult(
                answer=NO_DATA_ANSWER,
                sources=[],
                used_filters={
                    "answer_path": "embed_circuit_open",
                    "retrieval_sources": [],
                },
                fallback_level=0,
                intent="factual",
                answer_path="embed_circuit_open",
                retrieval_sources=[],
            )
            return RAGKernelOutput(
                result=result,
                events=[RAGEvent("embed_circuit_open", {"factory_id": rf.factory_id if rf else None})],
                degradation=circuit_open_degradation(fail_closed=True),
            )

        guarded = replace(
            inp,
            skip_llm=circuit.skip_llm,
            force_rerank_degraded=circuit.force_rerank_degraded,
            embed_breaker_open=circuit.embed_breaker_open,
            allow_scope_broadening=allow_broadening,
            circuit_enabled=circuit_enabled,
            circuit_mode=circuit.mode.value,
            safety_intent=safety.kind.value,
            entry_degradation=(
                circuit_open_degradation(fail_closed=safety.kind.value != "none")
                if circuit.skip_llm
                else None
            ),
        )
        return guarded

    async def run(
        self,
        inp: RAGKernelInput,
        *,
        executor: RAGKernelExecutor,
    ) -> AsyncIterator[str | RAGKernelOutput]:
        guarded = await self._apply_entry_guardrails(inp)
        if isinstance(guarded, RAGKernelOutput):
            if inp.stream:
                yield guarded.result.answer
            yield guarded
            return

        inp = guarded
        if inp.stream:
            async for item in executor.execute_stream(inp):
                yield item
            return
        output = await executor.execute_sync(inp)
        if inp.entry_degradation is not None and output.degradation is None:
            output.degradation = inp.entry_degradation
        yield output


_kernel: RAGKernel | None = None


def get_rag_kernel() -> RAGKernel:
    global _kernel
    if _kernel is None:
        _kernel = RAGKernel()
    return _kernel
