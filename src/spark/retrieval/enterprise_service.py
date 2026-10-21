"""Enterprise/HR RAG service — dense-only retrieval for enterprise collection."""

from __future__ import annotations

import re
import time
from collections.abc import AsyncIterator
from dataclasses import replace
from typing import Any

from spark.core.config import settings
from spark.core.lazy_singleton import lazy_singleton
from spark.core.llm_client import get_pipeline_llm
from spark.core.logging import get_logger
from spark.generation.pipeline import build_generation_input, grounded_generate_with_enforced_citations
from spark.generation.policy import resolve_generation_policy
from spark.generation.prompts_pipeline import enterprise_rag_prompt
from spark.ingestion.embedder import Embedder
from spark.retrieval.constants import NO_DATA_ANSWER
from spark.retrieval.context_budget import build_rag_context_budget, fit_docs_to_budget
from spark.retrieval.models import (
    RAGFilter,
    RAGResult,
    RAGStreamCitationBlock,
    RAGStreamPhaseMeta,
    RAGStreamToken,
    RetrievedDoc,
    _payload_to_source,
)
from spark.retrieval.synthesis import _order_docs_for_context, _select_sources_for_display

log = get_logger(__name__)

_ENTERPRISE_DOC_RELEVANCE_THRESHOLD = 0.35

_CHITCHAT_PATTERNS: list[re.Pattern[str]] = [
    re.compile(
        r"(?:^|\s)(?:สวัสดี|หวัดดี|ดีจ้า|ดีครับ|ดีค่ะ|ดีเจ้า|hello|hi|hey|yo)[\s!?ๆครับค่ะนะจ้า]*$",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:^|\s)(?:ขอบคุณ|ขอบใจ|thanks?|thank you|thx)[\s!?ครับค่ะนะจ้า]*$",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:คุณ(?:คือ|เป็น|ชื่อ)|neo\s*(?:คือ|เป็น|ชื่อ)|(?:you(?:'re| are)|what(?:'s| is) your name|who are you))",
        re.IGNORECASE,
    ),
    # Assistant-capability question — must be ABOUT the assistant. The old
    # unanchored form matched real machine how-to questions ("เครื่องนี้ใช้ยังไง",
    # "เครื่องนี้ทำอะไรได้บ้าง") and shunted them to a chitchat non-answer, so it
    # now requires an assistant referent (คุณ/neo/you) or a bare standalone
    # capability question. "ใช้ยังไง/ใช้อย่างไร" is dropped entirely — in a
    # factory assistant it is a how-to that must reach retrieval.
    re.compile(
        r"(?:^|\s)(?:คุณ|neo|น้อง\s*neo|เธอ|นาย|ยู|you)\s*"
        r"(?:ทำอะไรได้|ช่วยอะไรได้|มีความสามารถ|ช่วยอะไร|(?:can you|what can you)\s*do)",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(?:ทำอะไรได้บ้าง|ช่วยอะไรได้บ้าง|มีความสามารถอะไร(?:บ้าง)?|what can you do)"
        r"[\s!?ครับค่ะนะจ้า]*$",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:^|\s)(?:ลาก่อน|บ๊ายบาย|bye|goodbye|see you|ไว้เจอกัน|แล้วเจอกัน)[\s!?ครับค่ะนะจ้า]*$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(?:เป็นไง|สบายดี|สบายดีไหม|เป็นยังไง|how are you|how's it going)[\s!?ครับค่ะมั้ย]*$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(?:ok|โอเค|ได้เลย|เข้าใจแล้ว|รับทราบ|เข้าใจ|ครับ|ค่ะ|noted)[\s!?ครับค่ะ]*$",
        re.IGNORECASE,
    ),
]


def _is_chitchat(question: str) -> bool:
    q = question.strip()
    if len(q) > 120:
        return False
    return any(p.search(q) for p in _CHITCHAT_PATTERNS)


def _filter_relevant_docs(
    docs: list[RetrievedDoc],
    threshold: float = _ENTERPRISE_DOC_RELEVANCE_THRESHOLD,
) -> list[RetrievedDoc]:
    return [d for d in docs if d.score >= threshold]


class EnterpriseRAGService:
    """Simplified RAG pipeline for enterprise/HR documents.

    Dense-only vector search against ``spark_enterprise_docs``.
    No fallback ladder, no lexical leg, no scope broadening.
    """

    @property
    def embedder(self) -> Embedder:
        return Embedder.get()

    def _get_llm(self):
        return get_pipeline_llm("enterprise")

    async def _retrieve(
        self,
        query: str,
        rf: RAGFilter,
        top_k: int,
        allowed_doc_ids: list[str] | None = None,
    ) -> list[RetrievedDoc]:
        import asyncio

        from spark.retrieval.intent.glossary import expand_lexical_variants
        from spark.retrieval.vector.enterprise_search import search_enterprise_dense

        async def _leg(dense_query: str):
            return await search_enterprise_dense(
                query=dense_query,
                rf=rf,
                top_k=top_k,
                embedder=self.embedder,
                allowed_doc_ids=allowed_doc_ids,
            )

        # Multi-query dense retrieval: HR handbooks mix Thai and English — when
        # the glossary adds variants, search both queries concurrently and merge
        # by best score so cross-lingual phrasing still finds its chunk.
        expanded = expand_lexical_variants(query)
        if expanded != query and bool(getattr(settings, "rag_multi_query_expansion", True)):
            result, expanded_result = await asyncio.gather(_leg(query), _leg(expanded))
        else:
            result, expanded_result = await _leg(query), None

        if result.embed_failed:
            log.warning("enterprise_embed_failed")
            return []

        hits = list(result.hits)
        if expanded_result is not None and not expanded_result.embed_failed:
            seen = {
                (d.payload.get("chunk_id") or id(d)): d for d in hits
            }
            for doc in expanded_result.hits:
                key = doc.payload.get("chunk_id") or id(doc)
                current = seen.get(key)
                if current is None:
                    hits.append(doc)
                    seen[key] = doc
                elif doc.score > current.score:
                    current.score = doc.score
            hits.sort(key=lambda d: float(d.score), reverse=True)
        return hits[: max(top_k * 2, top_k)]

    async def _generate_without_context(
        self,
        question: str,
        *,
        chat_history: list[tuple[str, str]] | None = None,
        usage_calls: list[dict[str, Any]] | None = None,
    ) -> str:
        """Call LLM with enterprise prompt but no retrieved context.

        Allows the HR persona to handle greetings, chitchat, and politely
        decline knowledge questions when the enterprise collection is empty.
        """
        import asyncio
        from spark.generation.context import llm_prompt_payload
        from spark.generation.usage import normalize_llm_usage

        payload = llm_prompt_payload(
            context="(ไม่มีเอกสารอ้างอิง — นี่เป็นคำถามประเภท B ตอบได้เลยตามความรู้ของ Neo อย่างเป็นมิตร ห้ามอ้างอิงเอกสารหรือใส่ citation ถ้าเป็นคำถามเกี่ยวกับนโยบายหรือระเบียบบริษัทให้แจ้งว่ายังไม่พบข้อมูลในระบบและแนะนำติดต่อฝ่ายบุคคล)",
            question=question,
            chat_history=chat_history,
        )
        try:
            formatted = await enterprise_rag_prompt.ainvoke(payload)
            llm = self._get_llm()
            response = await asyncio.wait_for(
                llm.ainvoke(formatted),
                timeout=float(settings.rag_llm_timeout_sec or 60),
            )
            usage = normalize_llm_usage(response, llm=llm, operation="enterprise_no_context")
            if usage and usage_calls is not None:
                usage_calls.append(usage)
            raw = response.content if hasattr(response, "content") else str(response)
            return str(raw or "").strip() or NO_DATA_ANSWER
        except Exception as exc:
            log.warning("enterprise_no_context_llm_failed", error=str(exc)[:200])
            return NO_DATA_ANSWER

    async def _apply_rerank(
        self,
        query: str,
        docs: list[RetrievedDoc],
        top_k: int,
    ) -> list[RetrievedDoc]:
        from spark.retrieval.rerank.pipeline import get_rerank_pipeline

        result = await get_rerank_pipeline().apply(
            query, docs, top_k, session_id=None, intent_plan=None
        )
        return result.docs

    async def query(
        self,
        question: str,
        rf: RAGFilter | None = None,
        top_k: int = 6,
        allowed_doc_ids: list[str] | None = None,
        *,
        synthesis_question: str | None = None,
        chat_history: list[tuple[str, str]] | None = None,
        **kwargs: Any,
    ) -> RAGResult:
        _start = time.perf_counter()
        rf = rf or RAGFilter()
        rf = replace(rf, document_category="enterprise")

        is_chat = _is_chitchat(question)
        if is_chat:
            log.info("enterprise_chitchat_detected", question=question[:80])

        docs: list[RetrievedDoc] = []
        if not is_chat:
            docs = await self._retrieve(question, rf, top_k, allowed_doc_ids)
            if docs:
                docs = await self._apply_rerank(question, docs, top_k)
            docs = _filter_relevant_docs(docs)

        if docs:
            ordered = _order_docs_for_context(question, docs)
            budget = build_rag_context_budget(question)
            trim = fit_docs_to_budget(ordered, budget.doc_budget_tokens)
            ordered = trim.docs

            policy = await resolve_generation_policy(rf)
            gen = await grounded_generate_with_enforced_citations(
                question=question,
                docs=ordered,
                llm=self._get_llm(),
                chat_history=chat_history,
                synthesis_question=synthesis_question,
                policy=policy,
                prompt_template=enterprise_rag_prompt,
            )
            answer = gen.answer
            answer_path = gen.answer_path
            llm_usage = gen.llm_usage
        else:
            from spark.generation.usage import summarize_llm_usage

            ordered = []
            usage_calls: list[dict[str, Any]] = []
            answer = await self._generate_without_context(
                question, chat_history=chat_history, usage_calls=usage_calls,
            )
            answer_path = "enterprise_chitchat" if is_chat else "enterprise_no_context"
            llm_usage = summarize_llm_usage(usage_calls)

        if docs and answer_path == "no_data":
            # Generation-time suppression: don't pair "ไม่พบข้อมูล" with source
            # cards from documents that didn't answer — say what was found in
            # text instead.
            from spark.retrieval.no_data import build_no_data_answer

            answer = build_no_data_answer(question, ordered, rf=rf)

        if not docs or answer_path == "no_data":
            sources: list[dict[str, Any]] = []
        elif gen.citations_verified and gen.cited_docs:
            from spark.retrieval.models import cited_docs_to_sources
            sources = cited_docs_to_sources(question, gen.cited_docs)
        else:
            display_docs = _select_sources_for_display(ordered, answer, question=question)
            sources = [_payload_to_source(d.payload, d) for d in display_docs]

        top_doc_score = max((d.score for d in docs), default=0.0)
        latency_ms = round((time.perf_counter() - _start) * 1000, 2)
        log.info(
            "enterprise_rag_answer",
            answer_path=answer_path,
            sources_count=len(sources),
            latency_ms=latency_ms,
        )

        used_filters = {"pipeline": "enterprise", "answer_path": answer_path}
        if llm_usage:
            used_filters["llm_usage"] = llm_usage
        return RAGResult(
            answer=answer,
            sources=sources,
            used_filters=used_filters,
            fallback_level=0,
            intent="factual",
            top_doc_score=top_doc_score,
            answer_path=answer_path,
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
        cancel_event: Any | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[str | RAGResult | RAGStreamPhaseMeta]:
        import asyncio
        from spark.generation.streaming import stream_grounded_answer
        from spark.retrieval.models import RAGStreamError

        _start = time.perf_counter()
        rf = rf or RAGFilter()
        rf = replace(rf, document_category="enterprise")

        is_chat = _is_chitchat(question)
        if is_chat:
            log.info("enterprise_chitchat_detected_stream", question=question[:80])

        docs: list[RetrievedDoc] = []
        if not is_chat:
            docs = await self._retrieve(question, rf, top_k, allowed_doc_ids)
            if docs:
                docs = await self._apply_rerank(question, docs, top_k)
            docs = _filter_relevant_docs(docs)

        yield RAGStreamPhaseMeta(retrieval_report=None, system_degradation=None)

        if not docs:
            from spark.generation.usage import summarize_llm_usage

            answer_path = "enterprise_chitchat" if is_chat else "enterprise_no_context"
            usage_calls: list[dict[str, Any]] = []
            answer = await self._generate_without_context(
                question, chat_history=chat_history, usage_calls=usage_calls,
            )
            llm_usage = summarize_llm_usage(usage_calls)
            used_filters = {"pipeline": "enterprise", "answer_path": answer_path}
            if llm_usage:
                used_filters["llm_usage"] = llm_usage
            yield answer
            yield RAGResult(
                answer=answer,
                sources=[],
                used_filters=used_filters,
                fallback_level=0,
                intent="factual",
                answer_path=answer_path,
            )
            return

        ordered = _order_docs_for_context(question, docs)
        budget = build_rag_context_budget(question)
        trim = fit_docs_to_budget(ordered, budget.doc_budget_tokens)
        ordered = trim.docs

        policy = await resolve_generation_policy(rf)
        inp = build_generation_input(
            question=question,
            docs=ordered,
            llm=self._get_llm(),
            chat_history=chat_history,
            synthesis_question=synthesis_question,
            policy=policy,
            prompt_template=enterprise_rag_prompt,
        )
        inp.cancel_event = cancel_event

        gen = None
        streamed = False
        async for event in stream_grounded_answer(inp):
            if cancel_event is not None and cancel_event.is_set():
                raise asyncio.CancelledError("enterprise stream cancelled")
            if event.kind == "token_provisional" and event.delta:
                streamed = True
                yield RAGStreamToken(event.delta, provisional=True)
            elif event.kind == "token" and event.delta:
                streamed = True
                yield RAGStreamToken(event.delta, provisional=False)
            elif event.kind == "citation_block" and event.result is not None:
                gen = event.result
                streamed = True
                yield RAGStreamCitationBlock(
                    text=event.result.answer,
                    citations_verified=bool(event.result.citations_verified),
                )
            elif event.kind == "error" and event.message:
                yield RAGStreamError(event.message, event.message)
                return
            elif event.kind == "done" and event.result is not None:
                gen = event.result

        if gen is None:
            from spark.generation.types import GroundedGenerateResult
            gen = GroundedGenerateResult(
                answer=NO_DATA_ANSWER,
                cited_docs=[],
                answer_path="no_data",
                citations_verified=False,
            )

        streamed_answer = gen.answer
        if gen.answer_path == "no_data" and (gen.answer or "").strip() == NO_DATA_ANSWER:
            from spark.retrieval.no_data import build_no_data_answer

            gen = replace(gen, answer=build_no_data_answer(question, ordered, rf=rf))

        if not streamed and gen.answer:
            yield gen.answer
        elif streamed and gen.answer and gen.answer != streamed_answer:
            # The terse NO_DATA already went out over the stream and the client
            # only swaps text on a citation block, so the near-miss docs and
            # search tips would otherwise reach storage but never the screen.
            yield RAGStreamCitationBlock(text=gen.answer, citations_verified=False)

        if gen.answer_path == "no_data":
            sources: list[dict[str, Any]] = []
        elif gen.citations_verified and gen.cited_docs:
            from spark.retrieval.models import cited_docs_to_sources
            sources = cited_docs_to_sources(question, gen.cited_docs)
        else:
            display_docs = _select_sources_for_display(ordered, gen.answer, question=question)
            sources = [_payload_to_source(d.payload, d) for d in display_docs]

        top_doc_score = max((d.score for d in docs), default=0.0)
        used_filters = {"pipeline": "enterprise", "answer_path": gen.answer_path}
        if getattr(gen, "llm_usage", None):
            used_filters["llm_usage"] = gen.llm_usage
        yield RAGResult(
            answer=gen.answer,
            sources=sources,
            used_filters=used_filters,
            fallback_level=0,
            intent="factual",
            top_doc_score=top_doc_score,
            answer_path=gen.answer_path,
        )


enterprise_rag_service = lazy_singleton(lambda: EnterpriseRAGService())
