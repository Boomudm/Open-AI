from __future__ import annotations

import time
import uuid
from collections.abc import AsyncIterator
from dataclasses import replace
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from spark.core.config import settings
from spark.core.logging import get_logger
from spark.core.security import Principal
from spark.db.models.chat import ChatMessage, ChatSession
from spark.schemas.rag import (
    AskRequest,
    AskResponse,
    RetrievalReportModel,
    SystemDegradationModel,
    sources_to_refs,
)
from spark.services.document_access_service import allowed_doc_ids_for_principal
from spark.services.intent_classifier import QuestionRouting, resolve_routing, routing_to_intent
from spark.services.chat_stream import (
    sse_citation_block,
    sse_connected,
    sse_done,
    sse_error,
    sse_meta,
    sse_sources,
    sse_token,
    sse_token_provisional,
)
from spark.services.rag_service import RAGFilter, UNAVAILABLE_ANSWER, rag_service
from spark.retrieval.preprocess.contextualize import (
    contextualize_question,
    source_labels_from_sources,
)
from spark.services.session_slots import (
    SessionSlots,
    extract_revision_from_question,
    log_slot_diff,
    merge_session_slots,
    persist_session_slots,
)
from spark.services.routing_shadow import (
    ShadowLegacySnapshot,
    persist_agentic_canary_log,
    schedule_agentic_shadow,
)
from spark.services.agentic_canary import (
    evaluate_safety_override,
    log_safety_override,
    record_agentic_outcome,
    should_serve_agentic,
)

log = get_logger(__name__)

_CHITCHAT_FALLBACK_ANSWER = (
    "คุยได้ครับ ผม Neo พร้อมช่วยค้นข้อมูลจากเอกสารโรงงาน คู่มือเครื่องจักร "
    "งานซ่อมบำรุง และเอกสารองค์กรครับ"
)
_ENTERPRISE_DOC_TYPES = frozenset(
    {
        "company_policy",
        "hr_handbook",
        "internal_guideline",
    }
)
_ENTERPRISE_QUESTION_HINTS = (
    "hr",
    "human resource",
    "policy",
    "leave",
    "salary",
    "benefit",
    "welfare",
    "overtime",
    "ลาป่วย",
    "ลาพักร้อน",
    "ลาคลอด",
    "ลาได้",
    "วันลา",
    "เงินเดือน",
    "สวัสดิการ",
    "ประกันสังคม",
    "โอที",
    "ค่าล่วงเวลา",
    "วันหยุด",
    "ฝ่ายบุคคล",
    "พนักงาน",
    "ระเบียบบริษัท",
    "นโยบายบริษัท",
    "เวลาทำงาน",
    "เข้างาน",
    "ออกงาน",
)
_MACHINERY_QUESTION_HINTS = (
    "machine",
    "machinery",
    "manual",
    "cnc",
    "plc",
    "servo",
    "sensor",
    "motor",
    "robot",
    "kuka",
    "kss",
    "alarm",
    "interlock",
    "jog",
    "wiring",
    "diagram",
    "เครื่องจักร",
    "คู่มือ",
    "เซอร์โว",
    "มอเตอร์",
    "เซนเซอร์",
    "หุ่นยนต์",
    "สัญญาณ",
    "วงจร",
    "สายไฟ",
    "ไดอะแกรม",
)


def _resolve_rag_top_k(req_top_k: int | None, tuning_top_k_default: int) -> int:
    if req_top_k is not None:
        return req_top_k
    return tuning_top_k_default


def _coerce_retrieval_report(raw: dict[str, Any] | None) -> RetrievalReportModel | None:
    if not raw:
        return None
    try:
        return RetrievalReportModel.model_validate(raw)
    except Exception:
        return None


def _coerce_system_degradation(raw: dict[str, Any] | None) -> SystemDegradationModel | None:
    if not raw:
        return None
    try:
        return SystemDegradationModel.model_validate(raw)
    except Exception:
        return None


_VERIFIED_STREAM_ANSWER_PATHS = frozenset(
    {
        "grounded_llm",
        "grounded_extractive",
        "grounded_paraphrase",
        "grounded_structured_safety",
        "agentic",
        "qa_cache_hit",
    }
)


def _citations_verified_for_answer_path(answer_path: str) -> bool:
    return answer_path in _VERIFIED_STREAM_ANSWER_PATHS


def _stream_trust_fields(
    *,
    rag_result: Any,
    used: dict[str, Any],
) -> tuple[bool, str]:
    answer_path = (
        str(rag_result.answer_path)
        if rag_result is not None and getattr(rag_result, "answer_path", None)
        else str(used.get("answer_path") or "")
    )
    if rag_result is not None and getattr(rag_result, "answer_path", None):
        citations_verified = answer_path in {
            "grounded_llm",
            "grounded_extractive",
            "grounded_paraphrase",
            "grounded_structured_safety",
        }
    else:
        citations_verified = _citations_verified_for_answer_path(answer_path)
    return citations_verified, answer_path


class ChatOrchestrator:
    """Stateful chat with multi-hop context carryover.

    - Inherits filter context from `session.context` for followups
    - Persists user + assistant messages
    - Routes to RAG (factual) or analytics (analytic) in P1
    - Phase 2: agentic canary when ROUTING_MODE=agentic and session in canary bucket
    """

    @staticmethod
    def _wants_enterprise_pipeline(merged_filter: RAGFilter) -> bool:
        """Enterprise (HR/policy) pipeline only for enterprise-scoped questions.

        Pipeline selection must not key on "is a machine locked" alone: with no
        machine selected, every question — including pure machinery questions —
        would go to the HR-buddy pipeline, which is scoped to the enterprise
        collection, finds nothing, and answers without citations. Machine
        selection is optional by product decision, so machinery questions must
        reach the machinery RAG pipeline even without a lock."""
        category = str(getattr(merged_filter, "document_category", "") or "").lower()
        doc_type = str(getattr(merged_filter, "document_type", "") or "").lower()
        return category == "enterprise" or doc_type in _ENTERPRISE_DOC_TYPES

    @staticmethod
    def _question_has_hint(question: str, hints: tuple[str, ...]) -> bool:
        q = (question or "").casefold()
        return any(h.casefold() in q for h in hints)

    async def _judge_scope(
        self,
        question: str,
        *,
        prior_user_question: str | None = None,
    ) -> str | None:
        """Single authoritative scope judge (chitchat/enterprise/machinery).

        Context-aware: when the turn is a follow-up, the previous user
        question is included so the judge routes by conversation topic rather
        than by an isolated, keyword-less phrase ("แล้วลากิจล่ะ"). Fails safe —
        any error/timeout returns None and the caller decides the default."""
        from spark.services.llm_judge import judge_one_word

        context_line = ""
        if prior_user_question and prior_user_question.strip():
            context_line = (
                f'\nบริบท: ก่อนหน้านี้ผู้ใช้ถามว่า "{prior_user_question.strip()[:200]}" '
                "หากคำถามใหม่เป็นการถามต่อเนื่อง ให้จัดประเภทตามบริบทเดิม"
            )
        try:
            return await judge_one_word(
                "จัดประเภทคำถามนี้ว่าเป็นการคุยทั่วไป, เอกสารองค์กร/HR, หรือเอกสารเครื่องจักร"
                f"{context_line}\nคำถาม: {question}",
                ["CHITCHAT", "ENTERPRISE", "MACHINERY"],
                timeout_sec=4.0,
            )
        except Exception:  # noqa: BLE001
            return None

    async def _route_question_scope(
        self,
        question: str,
        merged_filter: RAGFilter,
        *,
        is_followup: bool = False,
        prior_user_question: str | None = None,
        prior_scope: str | None = None,
    ) -> tuple[str, str, str | None]:
        """Unified answer-method router for unlocked-machine questions.

        Returns (scope, reason, direct_answer), scope ∈
        "chitchat" | "enterprise" | "machinery". One cascade, most-precise
        signal first:

        1. deterministic chitchat (greeting/thanks/identity) → direct reply.
        2. explicit enterprise scope from the request/session filter.
        3. an *unambiguous* single-sided keyword hint (no LLM) — the cheap
           fast path for the common case.
        4. one context-aware LLM judge — the authority for everything else,
           including questions carrying hints for both scopes. On a follow-up
           it sees the prior question, so scope stays with the conversation.
        5. judge unavailable → inherit the thread's established scope
           (``prior_scope``); absent that, default to machinery — it clarifies
           or declines safely, whereas the enterprise pipeline would answer a
           machine question with no documents."""
        from spark.retrieval.enterprise_service import _is_chitchat
        from spark.retrieval.preprocess.adaptive import classify_retrieval_need

        adaptive = classify_retrieval_need(question)
        if adaptive.decision != "retrieve" and adaptive.direct_answer:
            return "chitchat", str(adaptive.decision), adaptive.direct_answer

        if _is_chitchat(question):
            return "chitchat", "chitchat_auto_keywords", _CHITCHAT_FALLBACK_ANSWER

        if self._wants_enterprise_pipeline(merged_filter):
            return "enterprise", "enterprise_explicit_scope", None

        has_enterprise_hint = self._question_has_hint(question, _ENTERPRISE_QUESTION_HINTS)
        has_machine_hint = self._question_has_hint(question, _MACHINERY_QUESTION_HINTS)
        # Only a *single-sided* hint short-circuits the judge. When both fire
        # (e.g. "พนักงานเดินเครื่อง CNC อบรมอะไร") the question is genuinely
        # ambiguous — the old code blindly chose machinery; now the judge, with
        # conversation context, decides.
        if has_enterprise_hint and not has_machine_hint:
            return "enterprise", "enterprise_auto_keywords", None
        if has_machine_hint and not has_enterprise_hint:
            return "machinery", "machinery_auto_keywords", None

        verdict = await self._judge_scope(
            question,
            prior_user_question=prior_user_question if is_followup else None,
        )
        if verdict == "CHITCHAT":
            return "chitchat", "chitchat_auto_judge", _CHITCHAT_FALLBACK_ANSWER
        if verdict == "ENTERPRISE":
            return "enterprise", "enterprise_auto_judge", None
        if verdict == "MACHINERY":
            return "machinery", "machinery_auto_judge", None

        if prior_scope in ("enterprise", "machinery"):
            return prior_scope, f"sticky_default:{prior_scope}", None
        return "machinery", "machinery_default", None

    async def _should_route_enterprise(
        self,
        question: str,
        merged_filter: RAGFilter,
    ) -> tuple[bool, str]:
        route, reason, _ = await self._route_question_scope(question, merged_filter)
        return route == "enterprise", reason

    @staticmethod
    def _resolve_session_scope(
        session_obj: ChatSession,
        req: AskRequest,
    ) -> tuple[SessionSlots, RAGFilter, str | None]:
        locked_machine = req.filter.machine_id if req.filter and req.filter.machine_id else None
        slots, merged_filter = merge_session_slots(
            session_obj.context,
            req.filter,
            locked_machine_id=locked_machine,
        )
        revision_from_question = extract_revision_from_question(req.question)
        if revision_from_question and not merged_filter.revision:
            merged_filter = replace(
                merged_filter,
                revision=revision_from_question,
                latest_revision_only=False,
            )
        return slots, merged_filter, locked_machine

    @staticmethod
    def _schedule_shadow_if_enabled(snap: ShadowLegacySnapshot) -> None:
        # Post-answer housekeeping: by the time this runs the done frame is
        # already yielded — an exception here must never turn a delivered
        # answer into a user-visible stream error.
        try:
            if settings.routing_mode != "shadow":
                return
            schedule_agentic_shadow(snap)
        except Exception as exc:  # noqa: BLE001
            log.warning("routing_shadow_schedule_failed", error=str(exc)[:200])

    @staticmethod
    def _build_shadow_snapshot(
        *,
        session_id: Any,
        req: AskRequest,
        response: AskResponse,
        legacy_latency_ms: float,
        allowed_doc_ids: list[str] | None = None,
        allowed_factory_ids: list[str] | None = None,
    ) -> ShadowLegacySnapshot:
        from spark.services.qa_cache_service import filter_fingerprint

        used = response.used_filters or {}
        cache_id_raw = used.get("cache_id")
        legacy_cache_id: uuid.UUID | None = None
        if cache_id_raw:
            try:
                legacy_cache_id = uuid.UUID(str(cache_id_raw))
            except ValueError:
                legacy_cache_id = None
        factory_id = used.get("factory_id")
        machine_id = used.get("machine_id")
        document_type = used.get("document_type")
        fp: str | None = None
        if factory_id:
            fp = filter_fingerprint(
                factory_id=str(factory_id),
                machine_id=str(machine_id) if machine_id else None,
                doc_type=str(document_type) if document_type else None,
            )
        legacy_sources: list[dict[str, Any]] = []
        for source in response.sources or []:
            if hasattr(source, "model_dump"):
                legacy_sources.append(source.model_dump())
            elif isinstance(source, dict):
                legacy_sources.append(dict(source))
        return ShadowLegacySnapshot(
            question=req.question,
            legacy_route=response.route,
            legacy_answer=response.answer,
            legacy_sources=legacy_sources,
            routing_reason=response.routing_reason,
            legacy_cache_hit=bool(response.cache_hit),
            message_id=response.assistant_message_id,
            session_id=session_id,
            effective_question=used.get("effective_question"),
            factory_id=str(factory_id) if factory_id else None,
            machine_id=str(machine_id) if machine_id else None,
            document_type=str(document_type) if document_type else None,
            filter_fingerprint=fp,
            legacy_cache_id=legacy_cache_id,
            legacy_answer_path=str(
                used.get("answer_path") or used.get("sql_generation_path") or ""
            )
            or None,
            legacy_latency_ms=legacy_latency_ms,
            allowed_doc_ids=allowed_doc_ids,
            allowed_factory_ids=allowed_factory_ids,
        )

    async def _factory_rag_tuning(
        self, db: AsyncSession, factory_id: str | None, req_top_k: int | None
    ):
        from spark.services.factory_config_service import factory_config_service

        cfg = await factory_config_service.resolve(db, factory_id)
        tuning = factory_config_service.rag_tuning(cfg)
        top_k = _resolve_rag_top_k(req_top_k, tuning.top_k_default)
        return top_k, tuning

    async def _shadow_rbac_for_principal(
        self, db: AsyncSession, principal: Principal | None
    ) -> tuple[list[str] | None, list[str] | None]:
        if principal is None:
            return None, None
        allowed_factory_ids = (
            None if principal.is_admin else list(principal.factory_access.keys())
        )
        raw_ids = await allowed_doc_ids_for_principal(db, principal)
        allowed_doc_ids = None if raw_ids is None else [str(i) for i in raw_ids]
        return allowed_doc_ids, allowed_factory_ids

    async def ask(
        self,
        session_obj: ChatSession,
        req: AskRequest,
        db: AsyncSession,
        principal: Principal | None = None,
        *,
        attachment_context: str | None = None,
        existing_user_message: ChatMessage | None = None,
    ) -> AskResponse:
        from spark.observability.otel_tracing import set_span_error, start_span

        start = time.perf_counter()
        _chat_span_cm = start_span(
            "chat.ask",
            session_id=str(session_obj.session_id),
            factory_id=str((req.filter.factory_id if req.filter else None) or ""),
        )
        chat_span = _chat_span_cm.__enter__()
        try:
            if should_serve_agentic(session_obj.session_id):
                canary_response = await self._ask_agentic_canary(
                    session_obj,
                    req,
                    db,
                    principal,
                    start,
                    attachment_context=attachment_context,
                    existing_user_message=existing_user_message,
                )
                return canary_response

            response = await self._ask_impl(
                session_obj,
                req,
                db,
                principal,
                start,
                attachment_context=attachment_context,
                existing_user_message=existing_user_message,
            )
            allowed_doc_ids, allowed_factory_ids = await self._shadow_rbac_for_principal(
                db, principal
            )
            self._schedule_shadow_if_enabled(
                self._build_shadow_snapshot(
                    session_id=session_obj.session_id,
                    req=req,
                    response=response,
                    legacy_latency_ms=round((time.perf_counter() - start) * 1000, 2),
                    allowed_doc_ids=allowed_doc_ids,
                    allowed_factory_ids=allowed_factory_ids,
                )
            )
            return response
        except Exception as exc:
            if isinstance(exc, HTTPException):
                raise
            if isinstance(exc, NotImplementedError):
                raise
            set_span_error(chat_span, exc)
            log.error("chat_ask_failed", error=str(exc)[:500], exc_info=True)
            await db.rollback()
            self._log_chat_answer(
                intent="factual",
                answer_path="service_unavailable",
                retrieval_sources=[],
                latency_start=start,
                source_count=0,
                question=req.question,
            )
            return AskResponse(
                answer=UNAVAILABLE_ANSWER,
                sources=[],
                used_filters={},
                intent="factual",
                fallback_level=0,
            )
        finally:
            _chat_span_cm.__exit__(None, None, None)

    async def _ask_agentic_canary(
        self,
        session_obj: ChatSession,
        req: AskRequest,
        db: AsyncSession,
        principal: Principal | None,
        _start: float,
        *,
        attachment_context: str | None = None,
        existing_user_message: ChatMessage | None = None,
    ) -> AskResponse:
        """Serve user-facing agentic path for canary sessions (Phase 2)."""
        slots, merged_filter, locked_machine = self._resolve_session_scope(session_obj, req)
        if existing_user_message is not None:
            user_msg = existing_user_message
        else:
            user_msg = ChatMessage(
                session_id=session_obj.session_id,
                role="user",
                content=req.question,
                sources=None,
            )
            db.add(user_msg)
            await db.flush()

        prior_messages = await self._recent_messages(
            db,
            session_obj.session_id,
            exclude_message_id=user_msg.message_id,
        )
        routing = await resolve_routing(
            req.question,
            document_type=merged_filter.document_type,
            has_prior_user_message=any(m.role == "user" for m in prior_messages),
        )
        intent = routing_to_intent(routing)
        effective_question = self._contextualize_question(
            req.question,
            routing,
            merged_filter,
            prior_messages,
        )
        if attachment_context:
            effective_question = f"{effective_question}\n\n{attachment_context}"

        from spark.services.question_analytics_service import record_question_analytics

        await record_question_analytics(
            db,
            message_id=user_msg.message_id,
            question=req.question,
            intent=intent,
            merged_filter=merged_filter,
        )

        allowed_doc_ids, allowed_factory_ids = await self._shadow_rbac_for_principal(db, principal)
        from spark.services.agentic.types import DatabaseScope, RBACContext, SearchFilters

        filters = SearchFilters(
            factory_id=merged_filter.factory_id,
            machine_id=merged_filter.machine_id,
            document_type=merged_filter.document_type,
            language=merged_filter.language,
            only_active=merged_filter.only_active,
            latest_revision_only=merged_filter.latest_revision_only,
        )
        scope = DatabaseScope(
            factory_id=merged_filter.factory_id,
            machine_id=merged_filter.machine_id,
        )
        rbac = RBACContext(
            allowed_doc_ids=allowed_doc_ids,
            allowed_factory_ids=allowed_factory_ids,
        )

        agentic_start = time.perf_counter()
        agentic: dict[str, Any] | None = None
        agentic_error: str | None = None
        try:
            from spark.services.agentic.tools import run_agentic_tools_parallel

            agentic = await run_agentic_tools_parallel(
                query=effective_question,
                filters=filters,
                scope=scope,
                rbac_context=rbac,
            )
        except Exception as exc:
            agentic_error = str(exc)[:500]
            log.error("agentic_canary_failed", error=agentic_error, question=req.question[:80])
            record_agentic_outcome(None, agentic_error=agentic_error)
            return await self._ask_impl(
                session_obj,
                req,
                db,
                principal,
                _start,
                attachment_context=attachment_context,
                existing_user_message=user_msg,
            )

        agentic_latency_ms = round((time.perf_counter() - agentic_start) * 1000, 2)
        override = evaluate_safety_override(req.question, agentic)
        if override.override:
            log_safety_override(req.question, override.reason)
            record_agentic_outcome(agentic, agentic_error=override.reason)
            legacy_response = await self._ask_impl(
                session_obj,
                req,
                db,
                principal,
                _start,
                attachment_context=attachment_context,
                existing_user_message=user_msg,
            )
            snap = self._build_shadow_snapshot(
                session_id=session_obj.session_id,
                req=req,
                response=legacy_response,
                legacy_latency_ms=round((time.perf_counter() - _start) * 1000, 2),
                allowed_doc_ids=allowed_doc_ids,
                allowed_factory_ids=allowed_factory_ids,
            )
            await persist_agentic_canary_log(
                snap,
                agentic,
                agentic_error=override.reason,
                agentic_latency_ms=agentic_latency_ms,
            )
            return legacy_response

        record_agentic_outcome(agentic, agentic_error=agentic_error)
        answer = str(agentic.get("agentic_answer") or "")
        sources: list[dict[str, Any]] = list(agentic.get("agentic_sources") or [])
        answer_path = str(agentic.get("agentic_answer_path") or "agentic")
        used: dict[str, Any] = {
            "route": "agentic",
            "routing_reason": "canary:agentic",
            "answer_path": answer_path,
            "agentic_tools_called": agentic.get("agentic_tools_called"),
            "effective_question": effective_question,
            "factory_id": merged_filter.factory_id,
            "machine_id": merged_filter.machine_id,
            "document_type": merged_filter.document_type,
        }

        from spark.retrieval.confidence import confidence_from_rag, confidence_payload

        conf = confidence_from_rag(
            top_doc_score=1.0 if sources else 0.0,
            source_count=len(sources),
            fallback_level=0,
        )
        confidence_tier = conf.tier
        used.update(confidence_payload(conf))

        llm_usage = used.get("llm_usage") if isinstance(used, dict) else None
        retrieval_snapshot: dict[str, Any] | None = {"llm_usage": llm_usage} if llm_usage else None

        asst_msg = ChatMessage(
            session_id=session_obj.session_id,
            role="assistant",
            content=answer,
            sources=sources or None,
            confidence_tier=confidence_tier,
            cache_hit=False,
            retrieval_snapshot=retrieval_snapshot,
        )
        db.add(asst_msg)
        await db.flush()
        before_slots = slots
        slots = slots.apply_turn(
            question=req.question,
            rf=merged_filter,
            chunk_ids=[],
            locked_machine_id=locked_machine,
        )
        log_slot_diff(before_slots, slots)
        session_obj.context = persist_session_slots(session_obj.context, slots)

        from spark.services.session_title_service import generate_session_title, is_default_title as _is_default_ag

        has_prior_user_ag = any(m.role == "user" for m in prior_messages)
        session_row_ag = await db.get(ChatSession, session_obj.session_id)
        if session_row_ag is not None and _is_default_ag(session_row_ag.title) and not has_prior_user_ag:
            session_row_ag.title = await generate_session_title(
                req.question,
                machine_id=merged_filter.machine_id,
            )
        await db.commit()

        response = AskResponse(
            answer=answer,
            sources=sources_to_refs(sources) if sources else [],
            used_filters=self._with_effective_question(used, req.question, effective_question),
            intent=intent,
            route="agentic",
            routing_reason="canary:agentic",
            fallback_level=0,
            cache_hit=False,
            assistant_message_id=asst_msg.message_id,
            top_doc_score=conf.top_doc_score,
            confidence_tier=confidence_tier,
        )
        snap = self._build_shadow_snapshot(
            session_id=session_obj.session_id,
            req=req,
            response=response,
            legacy_latency_ms=0.0,
            allowed_doc_ids=allowed_doc_ids,
            allowed_factory_ids=allowed_factory_ids,
        )
        snap = replace(
            snap,
            legacy_answer="[canary: agentic served]",
            legacy_route="agentic",
        )
        await persist_agentic_canary_log(
            snap,
            agentic,
            agentic_error=agentic_error,
            agentic_latency_ms=agentic_latency_ms,
        )
        self._log_chat_answer(
            intent=intent,
            answer_path=answer_path,
            retrieval_sources=[],
            latency_start=_start,
            source_count=len(sources),
            question=req.question,
        )
        return response

    async def _ask_impl(
        self,
        session_obj: ChatSession,
        req: AskRequest,
        db: AsyncSession,
        principal: Principal | None,
        _start: float,
        *,
        attachment_context: str | None = None,
        existing_user_message: ChatMessage | None = None,
    ) -> AskResponse:
        slots, merged_filter, locked_machine = self._resolve_session_scope(session_obj, req)

        if existing_user_message is not None:
            user_msg = existing_user_message
        else:
            user_msg = ChatMessage(
                session_id=session_obj.session_id,
                role="user",
                content=req.question,
                sources=None,
            )
            db.add(user_msg)
            await db.flush()
        prior_messages = await self._recent_messages(
            db,
            session_obj.session_id,
            exclude_message_id=user_msg.message_id,
        )
        has_prior_user = any(m.role == "user" for m in prior_messages)
        routing = await resolve_routing(
            req.question,
            document_type=merged_filter.document_type,
            has_prior_user_message=has_prior_user,
        )
        intent = routing_to_intent(routing)
        last_user = next((m for m in reversed(prior_messages) if m.role == "user"), None)
        last_assistant = next(
            (m for m in reversed(prior_messages) if m.role == "assistant"),
            None,
        )
        effective_question = contextualize_question(
            req.question,
            is_followup=routing.is_followup,
            rf=merged_filter,
            prior_user_content=last_user.content if last_user else None,
            prior_user_contents=self._prior_user_contents(prior_messages),
            source_labels=source_labels_from_sources(
                last_assistant.sources if last_assistant else None
            ),
        )
        if attachment_context:
            effective_question = f"{effective_question}\n\n{attachment_context}"

        from spark.services.question_analytics_service import record_question_analytics

        await record_question_analytics(
            db,
            message_id=user_msg.message_id,
            question=req.question,
            intent=intent,
            merged_filter=merged_filter,
        )

        retrieval_snapshot = None
        retrieval_report_model: RetrievalReportModel | None = None
        system_degradation_model: SystemDegradationModel | None = None

        from spark.retrieval.enterprise_service import _is_chitchat

        is_general_chat = _is_chitchat(req.question)

        from spark.services.external_sql_routing import try_external_analytics

        external_result = None
        if not is_general_chat:
            external_result = await try_external_analytics(
                db,
                effective_question,
                routing,
                factory_id=merged_filter.factory_id,
                job_position_ids=list(principal.job_position_ids) if principal else None,
            )

        # Mixed compound (SQL + document parts): the analytic parts are already
        # answered in external_result's sql_sections; the document remainder
        # continues through the RAG pipelines below and both merge at the end.
        external_sql_sections: dict[str, Any] | None = None
        if external_result is not None and external_result.get("residual_question"):
            external_sql_sections = external_result
            effective_question = str(external_result["residual_question"])
            external_result = None

        route_scope = "machinery" if locked_machine else None
        route_reason: str | None = None
        route_direct_answer: str | None = None
        # General chat routes through the scope cascade too: its first two rungs
        # (adaptive + keyword chitchat) return an instant canned reply. Sending
        # it to the enterprise pipeline instead had the LLM free-associate over
        # chat history — a bare "ขอบคุณครับ" got a re-explanation of the
        # previous answer rather than an acknowledgement.
        if not locked_machine and external_result is None:
            route_scope, route_reason, route_direct_answer = await self._route_question_scope(
                effective_question if external_sql_sections is not None else req.question,
                merged_filter,
                is_followup=routing.is_followup,
                prior_user_question=last_user.content if last_user else None,
                prior_scope=slots.pipeline,
            )
        use_machinery_pipeline = locked_machine is not None or route_scope == "machinery"
        resolved_scope = (
            "machinery"
            if use_machinery_pipeline
            else ("enterprise" if route_scope == "enterprise" else None)
        )

        if is_general_chat and locked_machine:
            from spark.retrieval.enterprise_service import enterprise_rag_service
            from spark.generation.usage import summarize_llm_usage

            chat_history = self._build_chat_history(prior_messages, effective_question)
            usage_calls: list[dict[str, Any]] = []
            answer = await enterprise_rag_service._generate_without_context(
                req.question, chat_history=chat_history, usage_calls=usage_calls,
            )
            llm_usage = summarize_llm_usage(usage_calls)
            sources: list[dict[str, Any]] = []
            used = {
                "route": "rag",
                "routing_reason": "chitchat_bypass",
                "pipeline": "enterprise",
                "answer_path": "enterprise_chitchat",
            }
            if llm_usage:
                used["llm_usage"] = llm_usage
            fallback_level = 0
            top_doc_score = 0.0
            from spark.retrieval.confidence import confidence_from_rag, confidence_payload

            conf = confidence_from_rag(
                top_doc_score=0.0,
                source_count=0,
                fallback_level=0,
            )
            confidence_tier = conf.tier
            used.update(confidence_payload(conf))
            cache_hit = False

        elif route_scope == "chitchat" and route_direct_answer:
            # Greeting/thanks/meta — answer directly; running a retrieval
            # pipeline here dumps unrelated document summaries at the user.
            from spark.retrieval.confidence import confidence_from_rag, confidence_payload

            answer = route_direct_answer
            sources = []
            used = {
                "route": "rag",
                "routing_reason": route_reason or "chitchat_direct",
                "pipeline": "chitchat",
                "answer_path": "chitchat_direct",
            }
            fallback_level = 0
            top_doc_score = 0.0
            intent = "chitchat"
            conf = confidence_from_rag(top_doc_score=0.0, source_count=0, fallback_level=0)
            confidence_tier = conf.tier
            used.update(confidence_payload(conf))
            cache_hit = False

        elif external_result is not None:
            answer = external_result["answer"]
            sources = []
            used = {
                "sql": external_result.get("sql"),
                "row_count": external_result.get("row_count"),
                "reason_code": external_result.get("reason_code"),
                "sql_generation_path": external_result.get("sql_generation_path"),
                "answer_path": external_result.get("sql_generation_path") or "external_sql",
                "route": "sql",
                "routing_reason": "external_data_source",
                "pipeline": "external_sql",
                "data_source_id": external_result.get("data_source_id"),
                "data_source_name": external_result.get("data_source_name"),
            }
            fallback_level = 0 if external_result.get("reason_code") == "ok" else 1
            from spark.retrieval.confidence import confidence_from_sql, confidence_payload

            conf = confidence_from_sql(
                reason_code=external_result.get("reason_code"),
                row_count=external_result.get("row_count"),
                fallback_level=fallback_level,
                answer_path=external_result.get("sql_generation_path") or "external_sql",
            )
            confidence_tier = conf.tier
            top_doc_score = conf.top_doc_score
            used.update(confidence_payload(conf))
            cache_hit = False

        elif routing.route == "sql" and locked_machine:
            from spark.services.analytics_service import analytics_service

            allowed_factory_ids = (
                None
                if principal is None or principal.is_admin
                else list(principal.factory_access.keys())
            )
            result = await analytics_service.query(
                effective_question,
                factory_id=merged_filter.factory_id,
                machine_id=merged_filter.machine_id,
                allowed_factory_ids=allowed_factory_ids,
            )
            answer = result["answer"]
            sources: list[dict[str, Any]] = []
            used = {
                "sql": result.get("sql"),
                "row_count": result.get("row_count"),
                "reason_code": result.get("reason_code"),
                "sql_generation_path": result.get("sql_generation_path"),
                "answer_path": result.get("sql_generation_path") or "sql_unknown",
                "route": routing.route,
                "routing_reason": routing.reason,
            }
            fallback_level = 0 if result.get("reason_code") == "ok" else 1
            from spark.retrieval.confidence import confidence_from_sql, confidence_payload

            conf = confidence_from_sql(
                reason_code=result.get("reason_code"),
                row_count=result.get("row_count"),
                fallback_level=fallback_level,
            )
            confidence_tier = conf.tier
            top_doc_score = conf.top_doc_score
            used.update(confidence_payload(conf))
            cache_hit = False
            if result.get("reason_code") not in ("ok", None):
                log.info(
                    "analytics_orchestrator_fallback",
                    reason_code=result.get("reason_code"),
                    question=req.question[:80],
                )

        elif not use_machinery_pipeline:
            # --- Pipeline 2: Enterprise / HR Buddy ---
            from spark.retrieval.confidence import confidence_from_rag, confidence_payload
            from spark.retrieval.enterprise_service import enterprise_rag_service

            pipeline = "enterprise"
            cache_hit = False
            top_doc_score = 0.0
            allowed_doc_ids: list[str] | None = None
            if principal is not None:
                raw_ids = await allowed_doc_ids_for_principal(db, principal)
                allowed_doc_ids = None if raw_ids is None else [str(i) for i in raw_ids]

            ent_result = await enterprise_rag_service.query(
                question=effective_question,
                rf=merged_filter,
                top_k=req.top_k or 6,
                allowed_doc_ids=allowed_doc_ids,
                synthesis_question=effective_question,
                chat_history=self._build_chat_history(prior_messages, effective_question),
            )
            answer = ent_result.answer
            sources = ent_result.sources
            used = {
                **ent_result.used_filters,
                "route": "rag",
                "routing_reason": route_reason or "enterprise_pipeline",
                "pipeline": pipeline,
            }
            fallback_level = ent_result.fallback_level
            top_doc_score = ent_result.top_doc_score
            conf = confidence_from_rag(
                top_doc_score=top_doc_score,
                source_count=len(sources or []),
                fallback_level=fallback_level,
                answer_path=ent_result.answer_path or "grounded_llm",
                citations_verified=bool(sources)
                and (ent_result.answer_path or "") not in {"no_data", "llm_unavailable"},
            )
            confidence_tier = conf.tier
            used.update(confidence_payload(conf))

        else:
            # --- Pipeline 1: Machinery Expert ---
            from spark.retrieval.confidence import confidence_from_rag, confidence_payload

            cache_hit = False
            top_doc_score = 0.0
            allowed_doc_ids: list[str] | None = None
            if principal is not None:
                raw_ids = await allowed_doc_ids_for_principal(db, principal)
                allowed_doc_ids = None if raw_ids is None else [str(i) for i in raw_ids]
            cached = await self._lookup_validated_qa_cache(
                db,
                factory_id=merged_filter.factory_id,
                question=req.question,
                principal=principal,
                machine_id=merged_filter.machine_id,
                doc_type=getattr(merged_filter, "doc_type", None),
                allowed_doc_ids=allowed_doc_ids,
            )
            if cached:
                answer = cached["answer"]
                sources = cached["sources"]
                cache_hit = True
                from spark.retrieval.retrieval_snapshot import build_retrieval_snapshot
                from spark.services.session_slots import session_slots_hash

                retrieval_snapshot = build_retrieval_snapshot(
                    question_raw=req.question,
                    question_retrieval=req.question,
                    question_synthesis=effective_question,
                    fallback_level=0,
                    docs=[],
                    session_slots=slots.to_context_dict(),
                    cache_hit=True,
                    cache_fingerprint=cached.get("cache_fingerprint"),
                    session_slots_hash=session_slots_hash(slots),
                    rewrite_verdict="cache_bypass",
                )
                used = {
                    "route": routing.route,
                    "routing_reason": routing.reason,
                    "cache_id": cached.get("cache_id"),
                    "answer_path": "qa_cache_hit",
                }
                fallback_level = 0
                top_doc_score = 1.0
                conf = confidence_from_rag(
                    top_doc_score=top_doc_score,
                    source_count=len(sources),
                    fallback_level=fallback_level,
                )
            else:
                (
                    retrieval_question,
                    compressed,
                    chat_history,
                    rewrite_meta,
                ) = await self._prepare_rag_retrieval(
                    db=db,
                    # Mixed compound: retrieve for the document remainder only,
                    # or the SQL half pollutes the retrieval query.
                    question=req.question if external_sql_sections is None else effective_question,
                    effective_question=effective_question,
                    prior_messages=prior_messages,
                    session_slots=slots,
                    has_prior_user=has_prior_user,
                    factory_id=merged_filter.factory_id,
                )
                rag_top_k, rag_tuning = await self._factory_rag_tuning(
                    db, merged_filter.factory_id, req.top_k
                )
                user_id = str(principal.user_id) if principal and principal.user_id else None
                from spark.retrieval.safety.admission import rag_admission_guard

                follow_up_chunks = slots.follow_up_chunk_ids()
                async with rag_admission_guard(merged_filter.factory_id, user_id=user_id):
                    rag_result = await rag_service.query(
                        question=retrieval_question,
                        synthesis_question=effective_question,
                        rf=merged_filter,
                        top_k=rag_top_k,
                        allowed_doc_ids=allowed_doc_ids,
                        chat_history=chat_history,
                        tuning=rag_tuning,
                        allow_scope_broadening=req.allow_scope_broadening,
                        session_id=str(session_obj.session_id),
                        question_raw=req.question,
                        rewrite_meta=rewrite_meta,
                        session_slots=slots.to_context_dict(),
                        follow_up=bool(rewrite_meta.get("follow_up")) and bool(follow_up_chunks),
                        last_retrieved_chunk_ids=follow_up_chunks or None,
                    )
                answer = rag_result.answer
                sources = rag_result.sources
                retrieval_snapshot = rag_result.retrieval_snapshot
                retrieval_report_model = _coerce_retrieval_report(
                    getattr(rag_result, "retrieval_report", None)
                )
                system_degradation_model = _coerce_system_degradation(
                    getattr(rag_result, "system_degradation", None)
                )
                used = {
                    **rag_result.used_filters,
                    "route": routing.route,
                    "routing_reason": routing.reason,
                    "pipeline": "machinery",
                    "question_raw": req.question,
                    "question_retrieval": retrieval_question,
                }
                if compressed:
                    used["compressed_question"] = compressed
                used["query_rewrite"] = rewrite_meta
                fallback_level = rag_result.fallback_level
                top_doc_score = rag_result.top_doc_score
                conf = confidence_from_rag(
                    top_doc_score=top_doc_score,
                    source_count=len(sources or []),
                    fallback_level=fallback_level,
                    answer_path=rag_result.answer_path or "grounded_llm",
                    citations_verified=bool(sources)
                    and (rag_result.answer_path or "") not in {
                        "no_data",
                        "llm_unavailable",
                        "numeric_grounding_fail",
                        "nli_gate_fail",
                    },
                    rerank_degraded_policy=(rag_result.retrieval_report or {}).get(
                        "rerank_degraded_policy"
                    ),
                    system_degradation=rag_result.system_degradation,
                )
            confidence_tier = conf.tier
            used.update(confidence_payload(conf))

        if external_sql_sections is not None:
            from spark.services.external_sql_routing import merge_compound_answer

            answer = merge_compound_answer(external_sql_sections, answer)
            used = {
                **used,
                "pipeline": f"external_sql+{used.get('pipeline') or 'rag'}",
                "sql_compound": external_sql_sections.get("sql_sections"),
                "sql": external_sql_sections.get("sql"),
                "data_source_id": external_sql_sections.get("data_source_id"),
                "data_source_name": external_sql_sections.get("data_source_name"),
            }

        asst_msg = ChatMessage(
            session_id=session_obj.session_id,
            role="assistant",
            content=answer,
            sources=sources or None,
            confidence_tier=confidence_tier,
            cache_hit=cache_hit,
            retrieval_snapshot=retrieval_snapshot,
        )
        db.add(asst_msg)
        await db.flush()

        locked_machine = req.filter.machine_id if req.filter and req.filter.machine_id else None
        chunk_ids = list((retrieval_snapshot or {}).get("chunk_ids") or [])
        before_slots = slots
        slots = slots.apply_turn(
            question=req.question,
            rf=merged_filter,
            chunk_ids=chunk_ids,
            locked_machine_id=locked_machine,
            pipeline=resolved_scope,
        )
        log_slot_diff(before_slots, slots)
        session_obj.context = persist_session_slots(session_obj.context, slots)

        from spark.services.session_title_service import generate_session_title, is_default_title

        if is_default_title(session_obj.title):
            prior_user_count = int(
                (
                    await db.execute(
                        select(func.count())
                        .select_from(ChatMessage)
                        .where(
                            ChatMessage.session_id == session_obj.session_id,
                            ChatMessage.role == "user",
                            ChatMessage.message_id != user_msg.message_id,
                        )
                    )
                ).scalar_one()
            )
            if prior_user_count == 0:
                session_obj.title = await generate_session_title(
                    req.question,
                    machine_id=merged_filter.machine_id,
                )

        await db.commit()

        # The branch that produced the answer knows its real route (external
        # SQL sets "sql"); routing.route is always "rag" from the RAG-only
        # classifier, so prefer the branch's own value.
        effective_route = str(used.get("route") or routing.route)
        effective_routing_reason = str(used.get("routing_reason") or routing.reason)

        await self._record_audit(
            db,
            principal=principal,
            factory_id=merged_filter.factory_id,
            question=req.question,
            route=effective_route,
            sources=sources,
        )

        answer_path = str(used.get("answer_path") or ("unknown"))
        retrieval_sources = list(used.get("retrieval_sources") or [])
        self._log_chat_answer(
            intent=intent,
            answer_path=answer_path,
            retrieval_sources=retrieval_sources,
            latency_start=_start,
            source_count=len(sources or []),
            question=req.question,
        )

        response = AskResponse(
            answer=answer,
            sources=sources_to_refs(sources) if sources else [],
            used_filters=self._with_effective_question(used, req.question, effective_question),
            intent=intent,
            route=effective_route,
            routing_reason=effective_routing_reason,
            fallback_level=fallback_level,
            cache_hit=cache_hit,
            assistant_message_id=asst_msg.message_id,
            top_doc_score=top_doc_score,
            confidence_tier=confidence_tier,
            retrieval_report=retrieval_report_model,
            system_degradation=system_degradation_model,
        )
        return response

    async def ask_stream(
        self,
        session_obj: ChatSession,
        req: AskRequest,
        principal: Principal | None = None,
        *,
        cancel_event: Any | None = None,
    ) -> AsyncIterator[str]:
        """Stream chat answer as SSE frames (no request-scoped DB session)."""
        yield sse_connected()
        start = time.perf_counter()
        try:
            if should_serve_agentic(session_obj.session_id):
                async for frame in self._ask_agentic_stream_body(
                    session_obj, req, principal, start
                ):
                    yield frame
                return
            async for frame in self._ask_stream_impl(
                session_obj, req, principal, cancel_event=cancel_event
            ):
                yield frame
        except HTTPException as exc:
            yield sse_error("http_error", str(exc.detail))
        except Exception as exc:
            log.error("chat_ask_stream_failed", error=str(exc)[:500], exc_info=True)
            yield sse_error("service_unavailable", UNAVAILABLE_ANSWER)

    async def _ask_agentic_stream_body(
        self,
        session_obj: ChatSession,
        req: AskRequest,
        principal: Principal | None,
        start: float,
    ) -> AsyncIterator[str]:
        """Agentic canary — honest sync completion (no pseudo-chunk streaming)."""
        from spark.core.database import AsyncSessionLocal
        from spark.services.chat_ask_dedupe import finish_stream_ask

        yield sse_meta(
            {
                "intent": "factual",
                "route": "agentic",
                "routing_reason": "canary:agentic",
            }
        )
        try:
            async with AsyncSessionLocal() as db:
                response = await self._ask_agentic_canary(
                    session_obj, req, db, principal, start
                )
        except HTTPException:
            raise
        except Exception as exc:
            log.error("chat_agentic_stream_failed", error=str(exc)[:500], exc_info=True)
            async with AsyncSessionLocal() as db:
                response = await self._ask_impl(session_obj, req, db, principal, start)

        answer_path = str((response.used_filters or {}).get("answer_path") or response.route)
        citations_verified = _citations_verified_for_answer_path(answer_path)
        yield sse_sources(
            {
                "sources": [s.model_dump() for s in response.sources],
                "fallback_level": response.fallback_level,
                "used_filters": response.used_filters,
                "citations_verified": citations_verified,
                "answer_path": answer_path,
            }
        )
        yield sse_citation_block(response.answer, citations_verified=citations_verified)
        yield sse_done(
            {
                "assistant_message_id": str(response.assistant_message_id),
                "cache_hit": response.cache_hit,
                "intent": response.intent,
                "route": response.route,
                "top_doc_score": response.top_doc_score,
                "confidence_tier": response.confidence_tier,
                "citations_verified": citations_verified,
                "answer_path": answer_path,
            }
        )
        await finish_stream_ask(session_obj.session_id, req.question, response)
        self._log_chat_answer(
            intent=response.intent,
            answer_path=answer_path,
            retrieval_sources=list((response.used_filters or {}).get("retrieval_sources") or []),
            latency_start=start,
            source_count=len(response.sources or []),
            question=req.question,
        )

    async def _ask_stream_impl(
        self,
        session_obj: ChatSession,
        req: AskRequest,
        principal: Principal | None,
        *,
        cancel_event: Any | None = None,
    ) -> AsyncIterator[str]:
        start = time.perf_counter()
        async for frame in self._ask_stream_body(
            session_obj,
            req,
            principal,
            start,
            cancel_event=cancel_event,
        ):
            yield frame

    async def _ask_stream_body(
        self,
        session_obj: ChatSession,
        req: AskRequest,
        principal: Principal | None,
        start: float,
        *,
        cancel_event: Any | None = None,
    ) -> AsyncIterator[str]:
        from spark.core.database import AsyncSessionLocal
        from spark.retrieval.models import RAGStreamError, RAGStreamToken, RAGStreamCitationBlock

        session_id = session_obj.session_id
        async with AsyncSessionLocal() as db:
            slots, merged_filter, locked_machine = self._resolve_session_scope(session_obj, req)
            user_msg = ChatMessage(
                session_id=session_id,
                role="user",
                content=req.question,
                sources=None,
            )
            db.add(user_msg)
            await db.flush()
            prior_messages = await self._recent_messages(
                db,
                session_id,
                exclude_message_id=user_msg.message_id,
            )
            has_prior_user = any(m.role == "user" for m in prior_messages)
            routing = await resolve_routing(
                req.question,
                document_type=merged_filter.document_type,
                has_prior_user_message=has_prior_user,
            )
            intent = routing_to_intent(routing)
            last_user = next((m for m in reversed(prior_messages) if m.role == "user"), None)
            last_assistant = next(
                (m for m in reversed(prior_messages) if m.role == "assistant"),
                None,
            )
            effective_question = contextualize_question(
                req.question,
                is_followup=routing.is_followup,
                rf=merged_filter,
                prior_user_content=last_user.content if last_user else None,
                prior_user_contents=self._prior_user_contents(prior_messages),
                source_labels=source_labels_from_sources(
                    last_assistant.sources if last_assistant else None
                ),
            )

            from spark.services.question_analytics_service import record_question_analytics

            await record_question_analytics(
                db,
                message_id=user_msg.message_id,
                question=req.question,
                intent=intent,
                merged_filter=merged_filter,
            )
            await db.commit()

        from spark.retrieval.enterprise_service import _is_chitchat as _stream_is_chitchat

        is_general_chat_stream = _stream_is_chitchat(req.question)
        from spark.services.external_sql_routing import try_external_analytics

        external_result_stream = None
        if not is_general_chat_stream:
            async with AsyncSessionLocal() as db:
                external_result_stream = await try_external_analytics(
                    db,
                    effective_question,
                    routing,
                    factory_id=merged_filter.factory_id,
                    job_position_ids=list(principal.job_position_ids) if principal else None,
                )
                await db.commit()

        # Mixed compound: SQL parts answered; document remainder streams via RAG.
        external_sql_sections_stream: dict[str, Any] | None = None
        if external_result_stream is not None and external_result_stream.get(
            "residual_question"
        ):
            external_sql_sections_stream = external_result_stream
            effective_question = str(external_result_stream["residual_question"])
            external_result_stream = None

        route_scope_stream = "machinery" if locked_machine else None
        route_reason_stream: str | None = None
        route_direct_stream: str | None = None
        # See ask(): general chat must reach the chitchat-direct branch, not the
        # enterprise pipeline (whose LLM free-associates over chat history).
        if not locked_machine and external_result_stream is None:
            route_scope_stream, route_reason_stream, route_direct_stream = await self._route_question_scope(
                effective_question
                if external_sql_sections_stream is not None
                else req.question,
                merged_filter,
                is_followup=routing.is_followup,
                prior_user_question=last_user.content if last_user else None,
                prior_scope=slots.pipeline,
            )
        use_machinery_stream = (
            locked_machine is not None or route_scope_stream == "machinery"
        )
        resolved_scope_stream = (
            "machinery"
            if use_machinery_stream
            else ("enterprise" if route_scope_stream == "enterprise" else None)
        )

        pipeline = (
            "machinery"
            if (use_machinery_stream and not is_general_chat_stream)
            else "enterprise"
        )
        if external_result_stream is not None:
            pipeline = "external_sql"
        if route_scope_stream == "chitchat" and route_direct_stream:
            pipeline = "chitchat"
            intent = "chitchat"
        yield sse_meta(
            {
                "intent": intent,
                "route": "sql" if external_result_stream is not None else routing.route,
                "routing_reason": (
                    "external_data_source"
                    if external_result_stream is not None
                    else (
                        route_reason_stream
                        if pipeline == "chitchat" and route_reason_stream
                        else routing.reason
                    )
                ),
                "pipeline": pipeline,
            }
        )

        if external_sql_sections_stream is not None:
            # Mixed compound: stream the already-answered SQL sections (and the
            # residual question's header) before the RAG part streams under it.
            from spark.services.external_sql_routing import compound_prefix_text

            yield sse_token(compound_prefix_text(external_sql_sections_stream))

        answer = ""
        sources: list[dict[str, Any]] = []
        used: dict[str, Any] = {}
        fallback_level = 0
        top_doc_score = 0.0
        confidence_tier: str = "medium"
        cache_hit = False
        retrieval_snapshot = None
        retrieval_report_model: RetrievalReportModel | None = None
        system_degradation_model: SystemDegradationModel | None = None
        rag_result = None

        # Ask-the-user-back before answering when the request is ambiguous:
        # a vague question we cannot retrieve against, or (no machine locked)
        # evidence that straddles several machines. Multi-topic questions are
        # exempt from the machine check — decomposition answers each topic.
        chitchat_direct_stream = (
            route_scope_stream == "chitchat" and bool(route_direct_stream)
        )
        clarify_msg: str | None = None
        if (
            not is_general_chat_stream
            and external_result_stream is None
            and not chitchat_direct_stream
        ):
            from spark.generation.clarify import (
                VAGUE_MESSAGE,
                candidate_machines,
                clarify_machine_message,
                is_vague_question,
            )
            from spark.retrieval.preprocess.decompose import should_attempt_decomposition

            if is_vague_question(req.question, has_prior_user=has_prior_user):
                clarify_msg = VAGUE_MESSAGE
            elif (
                use_machinery_stream
                and merged_filter.machine_id is None
                and not should_attempt_decomposition(effective_question)
            ):
                cands = await candidate_machines(
                    effective_question,
                    factory_id=merged_filter.factory_id,
                    embedder=rag_service.embedder,
                )
                if len(cands) >= 2:
                    clarify_msg = clarify_machine_message(cands)

        if clarify_msg:
            from spark.retrieval.confidence import confidence_from_rag, confidence_payload

            yield sse_token(clarify_msg)
            answer = clarify_msg
            used = {
                "route": "clarify",
                "routing_reason": "clarification_requested",
                "pipeline": "clarify",
                "answer_path": "clarification",
            }
            conf = confidence_from_rag(top_doc_score=0.0, source_count=0, fallback_level=0)
            top_doc_score = conf.top_doc_score
            confidence_tier = conf.tier
            used.update(confidence_payload(conf))

        elif chitchat_direct_stream:
            # Greeting/thanks/meta — stream the direct answer; a retrieval
            # pipeline here dumps unrelated document summaries at the user.
            from spark.retrieval.confidence import confidence_from_rag, confidence_payload

            answer = route_direct_stream or ""
            yield sse_token(answer)
            used = {
                "route": "rag",
                "routing_reason": route_reason_stream or "chitchat_direct",
                "pipeline": "chitchat",
                "answer_path": "chitchat_direct",
            }
            conf = confidence_from_rag(top_doc_score=0.0, source_count=0, fallback_level=0)
            top_doc_score = conf.top_doc_score
            confidence_tier = conf.tier
            used.update(confidence_payload(conf))

        elif is_general_chat_stream and locked_machine:
            from spark.retrieval.enterprise_service import enterprise_rag_service as _ent_svc
            from spark.retrieval.confidence import confidence_from_rag, confidence_payload
            from spark.generation.usage import summarize_llm_usage

            chat_history_chitchat = self._build_chat_history(prior_messages, effective_question)
            usage_calls: list[dict[str, Any]] = []
            answer = await _ent_svc._generate_without_context(
                req.question, chat_history=chat_history_chitchat, usage_calls=usage_calls,
            )
            llm_usage = summarize_llm_usage(usage_calls)
            yield sse_token(answer)
            used = {
                "route": "rag",
                "routing_reason": "chitchat_bypass",
                "pipeline": "enterprise",
                "answer_path": "enterprise_chitchat",
            }
            if llm_usage:
                used["llm_usage"] = llm_usage
            conf = confidence_from_rag(top_doc_score=0.0, source_count=0, fallback_level=0)
            top_doc_score = conf.top_doc_score
            confidence_tier = conf.tier
            used.update(confidence_payload(conf))

        elif external_result_stream is not None:
            from spark.retrieval.confidence import confidence_from_sql, confidence_payload

            answer = external_result_stream["answer"]
            yield sse_token(answer)
            used = {
                "sql": external_result_stream.get("sql"),
                "row_count": external_result_stream.get("row_count"),
                "reason_code": external_result_stream.get("reason_code"),
                "sql_generation_path": external_result_stream.get("sql_generation_path"),
                "answer_path": external_result_stream.get("sql_generation_path") or "external_sql",
                "route": "sql",
                "routing_reason": "external_data_source",
                "pipeline": "external_sql",
                "data_source_id": external_result_stream.get("data_source_id"),
                "data_source_name": external_result_stream.get("data_source_name"),
            }
            fallback_level = 0 if external_result_stream.get("reason_code") == "ok" else 1
            conf = confidence_from_sql(
                reason_code=external_result_stream.get("reason_code"),
                row_count=external_result_stream.get("row_count"),
                fallback_level=fallback_level,
                answer_path=external_result_stream.get("sql_generation_path") or "external_sql",
            )
            top_doc_score = conf.top_doc_score
            confidence_tier = conf.tier
            used.update(confidence_payload(conf))

        elif routing.route == "sql" and locked_machine:
            from spark.services.analytics_service import analytics_service
            from spark.retrieval.confidence import confidence_from_sql, confidence_payload

            allowed_factory_ids = (
                None
                if principal is None or principal.is_admin
                else list(principal.factory_access.keys())
            )
            result = await analytics_service.query(
                effective_question,
                factory_id=merged_filter.factory_id,
                machine_id=merged_filter.machine_id,
                allowed_factory_ids=allowed_factory_ids,
            )
            answer = result["answer"]
            used = {
                "sql": result.get("sql"),
                "row_count": result.get("row_count"),
                "reason_code": result.get("reason_code"),
                "route": routing.route,
                "routing_reason": routing.reason,
            }
            fallback_level = 0 if result.get("reason_code") == "ok" else 1
            conf = confidence_from_sql(
                reason_code=result.get("reason_code"),
                row_count=result.get("row_count"),
                fallback_level=fallback_level,
            )
            top_doc_score = conf.top_doc_score
            confidence_tier = conf.tier
            used.update(confidence_payload(conf))
            yield sse_token(answer)
        elif not use_machinery_stream:
            # --- Enterprise / HR Buddy streaming pipeline ---
            from spark.retrieval.confidence import confidence_from_rag, confidence_payload
            from spark.retrieval.enterprise_service import enterprise_rag_service
            from spark.retrieval.models import RAGStreamPhaseMeta

            allowed_doc_ids: list[str] | None = None
            async with AsyncSessionLocal() as db:
                if principal is not None:
                    raw_ids = await allowed_doc_ids_for_principal(db, principal)
                    allowed_doc_ids = None if raw_ids is None else [str(i) for i in raw_ids]
                await db.commit()

            rag_result = None
            async for item in enterprise_rag_service.query_stream(
                question=effective_question,
                rf=merged_filter,
                top_k=req.top_k or 6,
                allowed_doc_ids=allowed_doc_ids,
                synthesis_question=effective_question,
                chat_history=self._build_chat_history(prior_messages, effective_question),
                cancel_event=cancel_event,
            ):
                if isinstance(item, RAGStreamPhaseMeta):
                    yield sse_meta(
                        {
                            "intent": intent,
                            "route": "rag",
                            "routing_reason": route_reason_stream or "enterprise_pipeline",
                            "pipeline": "enterprise",
                        }
                    )
                elif isinstance(item, RAGStreamError):
                    yield sse_error(item.code, item.message or item.code)
                    return
                elif isinstance(item, RAGStreamCitationBlock):
                    answer = item.text
                    yield sse_citation_block(
                        item.text,
                        citations_verified=item.citations_verified,
                    )
                elif isinstance(item, RAGStreamToken):
                    if item.provisional:
                        yield sse_token_provisional(item.delta)
                    else:
                        yield sse_token(item.delta)
                    answer += item.delta
                elif isinstance(item, str):
                    yield sse_token(item)
                    answer += item
                else:
                    rag_result = item
            if rag_result is None:
                raise RuntimeError("enterprise stream ended without result")
            answer = rag_result.answer
            sources = rag_result.sources
            used = {
                **rag_result.used_filters,
                "route": "rag",
                "routing_reason": route_reason_stream or "enterprise_pipeline",
                "pipeline": "enterprise",
            }
            fallback_level = rag_result.fallback_level
            conf = confidence_from_rag(
                top_doc_score=rag_result.top_doc_score,
                source_count=len(sources or []),
                fallback_level=fallback_level,
                answer_path=rag_result.answer_path or "grounded_llm",
                citations_verified=bool(sources)
                and (rag_result.answer_path or "") not in {"no_data", "llm_unavailable"},
            )
            top_doc_score = conf.top_doc_score
            confidence_tier = conf.tier
            used.update(confidence_payload(conf))
        else:
            # --- Machinery Expert streaming pipeline ---
            from spark.retrieval.confidence import confidence_from_rag, confidence_payload

            cache_hit = False
            allowed_doc_ids: list[str] | None = None
            cached = None
            retrieval_question = effective_question
            compressed = None
            chat_history: list[tuple[str, str]] = []
            rewrite_meta: dict[str, Any] = {}
            rag_top_k = req.top_k
            rag_tuning = None

            async with AsyncSessionLocal() as db:
                if principal is not None:
                    raw_ids = await allowed_doc_ids_for_principal(db, principal)
                    allowed_doc_ids = None if raw_ids is None else [str(i) for i in raw_ids]
                cached = await self._lookup_validated_qa_cache(
                    db,
                    factory_id=merged_filter.factory_id,
                    question=req.question,
                    principal=principal,
                    machine_id=merged_filter.machine_id,
                    doc_type=getattr(merged_filter, "doc_type", None),
                    allowed_doc_ids=allowed_doc_ids,
                )
                if not cached:
                    (
                        retrieval_question,
                        compressed,
                        chat_history,
                        rewrite_meta,
                    ) = await self._prepare_rag_retrieval(
                        db=db,
                        # Mixed compound: retrieve for the document remainder
                        # only, or the SQL half pollutes the retrieval query.
                        question=(
                            req.question
                            if external_sql_sections_stream is None
                            else effective_question
                        ),
                        effective_question=effective_question,
                        prior_messages=prior_messages,
                        session_slots=slots,
                        has_prior_user=has_prior_user,
                        factory_id=merged_filter.factory_id,
                    )
                    rag_top_k, rag_tuning = await self._factory_rag_tuning(
                        db, merged_filter.factory_id, req.top_k
                    )
                await db.commit()

            if cached:
                answer = cached["answer"]
                sources = cached["sources"]
                cache_hit = True
                from spark.retrieval.retrieval_snapshot import build_retrieval_snapshot
                from spark.services.session_slots import session_slots_hash

                retrieval_snapshot = build_retrieval_snapshot(
                    question_raw=req.question,
                    question_retrieval=req.question,
                    question_synthesis=effective_question,
                    fallback_level=0,
                    docs=[],
                    session_slots=slots.to_context_dict(),
                    cache_hit=True,
                    cache_fingerprint=cached.get("cache_fingerprint"),
                    session_slots_hash=session_slots_hash(slots),
                    rewrite_verdict="cache_bypass",
                )
                used = {
                    "route": routing.route,
                    "routing_reason": routing.reason,
                    "cache_id": cached.get("cache_id"),
                    "answer_path": "qa_cache_hit",
                }
                fallback_level = 0
                conf = confidence_from_rag(
                    top_doc_score=1.0,
                    source_count=len(sources or []),
                    fallback_level=0,
                )
                top_doc_score = conf.top_doc_score
                confidence_tier = conf.tier
                used.update(confidence_payload(conf))
                yield sse_token(answer)
            else:
                user_id = str(principal.user_id) if principal and principal.user_id else None
                from spark.retrieval.safety.admission import rag_admission_guard

                follow_up_chunks = slots.follow_up_chunk_ids()
                rag_result = None
                from spark.retrieval.models import RAGStreamPhaseMeta, RAGStreamCitationBlock

                async with rag_admission_guard(merged_filter.factory_id, user_id=user_id):
                    async for item in rag_service.query_stream(
                        question=retrieval_question,
                        synthesis_question=effective_question,
                        rf=merged_filter,
                        top_k=rag_top_k,
                        allowed_doc_ids=allowed_doc_ids,
                        chat_history=chat_history,
                        tuning=rag_tuning,
                        allow_scope_broadening=req.allow_scope_broadening,
                        session_id=str(session_obj.session_id),
                        question_raw=req.question,
                        rewrite_meta=rewrite_meta,
                        session_slots=slots.to_context_dict(),
                        follow_up=bool(rewrite_meta.get("follow_up")) and bool(follow_up_chunks),
                        last_retrieved_chunk_ids=follow_up_chunks or None,
                        cancel_event=cancel_event,
                    ):
                        if isinstance(item, RAGStreamPhaseMeta):
                            retrieval_report_model = _coerce_retrieval_report(
                                item.retrieval_report
                            )
                            system_degradation_model = _coerce_system_degradation(
                                item.system_degradation
                            )
                            phase = (
                                (item.retrieval_report or {}).get("phase")
                                if isinstance(item.retrieval_report, dict)
                                else None
                            )
                            yield sse_meta(
                                {
                                    "intent": intent,
                                    "route": routing.route,
                                    "routing_reason": routing.reason,
                                    "stream_phase": phase or "reading",
                                    "retrieval_report": (
                                        retrieval_report_model.model_dump()
                                        if retrieval_report_model
                                        else item.retrieval_report
                                    ),
                                    "system_degradation": (
                                        system_degradation_model.model_dump()
                                        if system_degradation_model
                                        else item.system_degradation
                                    ),
                                }
                            )
                        elif isinstance(item, RAGStreamError):
                            yield sse_error(item.code, item.message or item.code)
                            from spark.services.chat_ask_dedupe import finish_stream_ask

                            await finish_stream_ask(session_obj.session_id, req.question, None)
                            return
                        elif isinstance(item, RAGStreamCitationBlock):
                            answer = item.text
                            yield sse_citation_block(
                                item.text,
                                citations_verified=item.citations_verified,
                            )
                        elif isinstance(item, RAGStreamToken):
                            if item.provisional:
                                yield sse_token_provisional(item.delta)
                            else:
                                yield sse_token(item.delta)
                            answer += item.delta
                        elif isinstance(item, str):
                            yield sse_token(item)
                            answer += item
                        else:
                            rag_result = item
                if rag_result is None:
                    raise RuntimeError("rag stream ended without result")
                answer = rag_result.answer
                sources = rag_result.sources
                retrieval_snapshot = rag_result.retrieval_snapshot
                retrieval_report_model = _coerce_retrieval_report(
                    getattr(rag_result, "retrieval_report", None)
                )
                system_degradation_model = _coerce_system_degradation(
                    getattr(rag_result, "system_degradation", None)
                )
                used = {
                    **rag_result.used_filters,
                    "route": routing.route,
                    "routing_reason": routing.reason,
                    "pipeline": "machinery",
                    "question_raw": req.question,
                    "question_retrieval": retrieval_question,
                    "query_rewrite": rewrite_meta,
                }
                if compressed:
                    used["compressed_question"] = compressed
                fallback_level = rag_result.fallback_level
                conf = confidence_from_rag(
                    top_doc_score=rag_result.top_doc_score,
                    source_count=len(sources or []),
                    fallback_level=fallback_level,
                    answer_path=rag_result.answer_path or "grounded_llm",
                    citations_verified=bool(sources)
                    and (rag_result.answer_path or "") not in {
                        "no_data",
                        "llm_unavailable",
                        "numeric_grounding_fail",
                        "nli_gate_fail",
                    },
                    rerank_degraded_policy=(rag_result.retrieval_report or {}).get(
                        "rerank_degraded_policy"
                    ),
                    system_degradation=(
                        system_degradation_model.to_dict()
                        if system_degradation_model is not None
                        and hasattr(system_degradation_model, "to_dict")
                        else getattr(rag_result, "system_degradation", None)
                    ),
                )
                top_doc_score = conf.top_doc_score
                confidence_tier = conf.tier
                used.update(confidence_payload(conf))

        if external_sql_sections_stream is not None:
            from spark.services.external_sql_routing import merge_compound_answer

            answer = merge_compound_answer(external_sql_sections_stream, answer)
            used = {
                **used,
                "pipeline": f"external_sql+{used.get('pipeline') or 'rag'}",
                "sql_compound": external_sql_sections_stream.get("sql_sections"),
                "sql": external_sql_sections_stream.get("sql"),
                "data_source_id": external_sql_sections_stream.get("data_source_id"),
                "data_source_name": external_sql_sections_stream.get("data_source_name"),
            }

        assistant_message_id: uuid.UUID | None = None
        async with AsyncSessionLocal() as db:
            session_row = await db.get(ChatSession, session_id)
            llm_usage = used.get("llm_usage") if isinstance(used, dict) else None
            if llm_usage and isinstance(retrieval_snapshot, dict):
                retrieval_snapshot = {**retrieval_snapshot, "llm_usage": llm_usage}
            elif llm_usage:
                retrieval_snapshot = {"llm_usage": llm_usage}
            asst_msg = ChatMessage(
                session_id=session_id,
                role="assistant",
                content=answer,
                sources=sources or None,
                confidence_tier=confidence_tier,
                cache_hit=cache_hit,
                retrieval_snapshot=retrieval_snapshot,
            )
            db.add(asst_msg)
            await db.flush()
            locked_machine = req.filter.machine_id if req.filter and req.filter.machine_id else None
            chunk_ids = list((retrieval_snapshot or {}).get("chunk_ids") or [])
            before_slots = slots
            slots = slots.apply_turn(
                question=req.question,
                rf=merged_filter,
                chunk_ids=chunk_ids,
                locked_machine_id=locked_machine,
                pipeline=resolved_scope_stream,
            )
            log_slot_diff(before_slots, slots)
            if session_row is not None:
                session_row.context = persist_session_slots(session_row.context or {}, slots)
            # Same as _ask_impl: the answering branch's route wins over the
            # RAG-only classifier's constant "rag".
            effective_route = str(used.get("route") or routing.route)
            effective_routing_reason = str(used.get("routing_reason") or routing.reason)
            await self._record_audit(
                db,
                principal=principal,
                factory_id=merged_filter.factory_id,
                question=req.question,
                route=effective_route,
                sources=sources,
            )
            allowed_doc_ids_shadow, allowed_factory_ids = await self._shadow_rbac_for_principal(
                db, principal
            )
            if session_row is not None:
                from spark.services.session_title_service import generate_session_title, is_default_title as _is_default

                if _is_default(session_row.title) and not has_prior_user:
                    session_row.title = await generate_session_title(
                        req.question,
                        machine_id=merged_filter.machine_id,
                    )
            await db.commit()
            assistant_message_id = asst_msg.message_id

        from spark.schemas.rag import sources_to_refs

        citations_verified, answer_path = _stream_trust_fields(rag_result=rag_result, used=used)
        yield sse_sources(
            {
                "sources": [s.model_dump() for s in sources_to_refs(sources)],
                "fallback_level": fallback_level,
                "used_filters": self._with_effective_question(
                    used, req.question, effective_question
                ),
                "retrieval_report": (
                    retrieval_report_model.model_dump() if retrieval_report_model else None
                ),
                "system_degradation": (
                    system_degradation_model.model_dump()
                    if system_degradation_model
                    else None
                ),
                "citations_verified": citations_verified,
                "answer_path": answer_path,
                "generation_mode": str(used.get("generation_mode") or ""),
            }
        )
        yield sse_done(
            {
                "assistant_message_id": str(assistant_message_id),
                "cache_hit": cache_hit,
                "intent": intent,
                "route": effective_route,
                "top_doc_score": top_doc_score,
                "confidence_tier": confidence_tier,
                "citations_verified": citations_verified,
                "answer_path": answer_path,
                "system_degradation": (
                    system_degradation_model.model_dump()
                    if system_degradation_model
                    else None
                ),
            }
        )
        from spark.services.chat_ask_dedupe import finish_stream_ask

        response = AskResponse(
            answer=answer,
            sources=sources_to_refs(sources) if sources else [],
            used_filters=self._with_effective_question(
                used, req.question, effective_question
            ),
            intent=intent,
            route=effective_route,
            routing_reason=effective_routing_reason,
            fallback_level=fallback_level,
            cache_hit=cache_hit,
            assistant_message_id=assistant_message_id,
            top_doc_score=top_doc_score,
            confidence_tier=confidence_tier,
        )
        await finish_stream_ask(session_obj.session_id, req.question, response)
        self._log_chat_answer(
            intent=intent,
            answer_path=str(used.get("answer_path") or routing.route),
            retrieval_sources=list(used.get("retrieval_sources") or []),
            latency_start=start,
            source_count=len(sources or []),
            question=req.question,
        )
        self._schedule_shadow_if_enabled(
            self._build_shadow_snapshot(
                session_id=session_id,
                req=req,
                response=AskResponse(
                    answer=answer,
                    sources=sources_to_refs(sources) if sources else [],
                    used_filters=self._with_effective_question(
                        used, req.question, effective_question
                    ),
                    intent=intent,
                    route=effective_route,
                    routing_reason=effective_routing_reason,
                    fallback_level=fallback_level,
                    cache_hit=cache_hit,
                    assistant_message_id=assistant_message_id,
                    top_doc_score=top_doc_score,
                    confidence_tier=confidence_tier,
                ),
                legacy_latency_ms=round((time.perf_counter() - start) * 1000, 2),
                allowed_doc_ids=allowed_doc_ids_shadow,
                allowed_factory_ids=allowed_factory_ids,
            )
        )

    @staticmethod
    def _prior_user_contents(prior_messages: list[ChatMessage], limit: int = 3) -> list[str]:
        """Last few user turns oldest-first — lets follow-ups reference n-2/n-3 turns."""
        contents = [
            (m.content or "").strip()
            for m in ChatOrchestrator._without_chitchat_turns(prior_messages)
            if m.role == "user" and (m.content or "").strip()
        ]
        return contents[-limit:]

    @staticmethod
    def _without_chitchat_turns(prior_messages: list[ChatMessage]) -> list[ChatMessage]:
        """Drop Q+A pairs answered by a canned chitchat reply.

        A "พรุ่งนี้ฝนตกไหม" or "ขอบคุณครับ" turn carries no retrievable topic;
        left in the history it gets glued into follow-up rewrites and the
        synthesis scaffold, derailing retrieval for the real question."""
        from spark.retrieval.preprocess.adaptive import is_direct_chitchat_answer

        kept: list[ChatMessage] = []
        pending_user: ChatMessage | None = None
        for msg in prior_messages:
            if msg.role == "user":
                if pending_user is not None:
                    kept.append(pending_user)
                pending_user = msg
            elif msg.role == "assistant":
                if is_direct_chitchat_answer(msg.content or ""):
                    pending_user = None
                    continue
                if pending_user is not None:
                    kept.append(pending_user)
                    pending_user = None
                kept.append(msg)
            else:
                kept.append(msg)
        if pending_user is not None:
            kept.append(pending_user)
        return kept

    async def _recent_messages(
        self,
        db: AsyncSession,
        session_id: Any,
        *,
        exclude_message_id: Any,
        limit: int = 6,
    ) -> list[ChatMessage]:
        result = await db.execute(
            select(ChatMessage)
            .where(
                ChatMessage.session_id == session_id,
                ChatMessage.message_id != exclude_message_id,
            )
            .order_by(ChatMessage.created_at.desc())
            .limit(limit)
        )
        return list(reversed(result.scalars().all()))

    def _build_chat_history(
        self,
        prior_messages: list[ChatMessage],
        question_for_budget: str,
        *,
        compact_for_rewrite: bool = False,
    ) -> list[tuple[str, str]]:
        from spark.retrieval.context_budget import (
            ChatMessageSlice,
            build_rag_context_budget,
            fit_messages_to_budget,
        )

        # 8 messages = 4 turns. 4 (2 turns) made every n-2 back-reference
        # unanswerable; fit_messages_to_budget below still enforces the token
        # budget, so raising the cap only costs tokens when the budget allows.
        #
        # compact_for_rewrite: the rewrite only needs each user question plus
        # enough of the assistant reply to tell success from no-data — at full
        # 2000-char slices two long answers exhaust the token budget and
        # fit_messages_to_budget evicts the OLDEST turns, which are exactly the
        # antecedents a follow-up needs (observed live: "แล้ว…alarm นั้น" lost
        # its alarm turn and merged two unrelated ones instead).
        user_cap = 400 if compact_for_rewrite else 2000
        assistant_cap = 200 if compact_for_rewrite else 2000
        max_messages = min(settings.chat_history_max_turns * 2, 8)
        slices: list[ChatMessageSlice] = []
        for msg in self._without_chitchat_turns(prior_messages)[-max_messages:]:
            if msg.role == "user":
                slices.append(ChatMessageSlice("user", msg.content[:user_cap]))
            elif msg.role == "assistant":
                slices.append(ChatMessageSlice("assistant", (msg.content or "")[:assistant_cap]))
        budget = build_rag_context_budget(question_for_budget)
        fitted = fit_messages_to_budget(slices, budget.history_budget_tokens)
        history: list[tuple[str, str]] = []
        for item in fitted:
            role = "human" if item.role == "user" else "ai"
            history.append((role, item.content))
        return history

    async def _prepare_rag_retrieval(
        self,
        *,
        db: AsyncSession,
        question: str,
        effective_question: str,
        prior_messages: list[ChatMessage],
        session_slots: SessionSlots,
        has_prior_user: bool,
        factory_id: str | None,
    ) -> tuple[str, str | None, list[tuple[str, str]], dict[str, Any]]:
        from spark.core.production_profile import ProductionProfile
        from spark.retrieval.preprocess.compress import maybe_compress_question
        from spark.retrieval.preprocess.rewrite import rewrite_for_retrieval
        from spark.services.factory_config_service import factory_config_service

        chat_history = self._build_chat_history(prior_messages, effective_question)
        rewrite_history = self._build_chat_history(
            prior_messages, effective_question, compact_for_rewrite=True
        )
        factory_cfg = await factory_config_service.resolve(db, factory_id)
        profile = ProductionProfile.for_factory(factory_cfg)
        # Rewrite the user's own question, never `effective_question`: the latter
        # is a generation-prompt scaffold ("factory_id: F-05\nคำถามก่อนหน้า: …")
        # that belongs in synthesis_question alone. Fed in here it survives into
        # the retrieval question, where the compound splitter cuts it along its
        # own newlines and answers the scaffold labels as if they were topics —
        # the user sees "factory_id: F-05 machine_id: SV-01 คำถามก่อนหน้า:" as a
        # sub-question heading. The follow-up context it carries is redundant:
        # chat_history and session_slots below already supply it.
        rewritten, rewrite_meta = await rewrite_for_retrieval(
            question,
            rewrite_history,
            session_slots,
            llm_rewrite_enabled=profile.query_rewrite_enabled,
            has_prior_user_message=has_prior_user,
        )
        retrieval_question, compressed = await maybe_compress_question(rewritten)
        if compressed:
            rewrite_meta["compressed_question"] = compressed
        log.info(
            "query_rewrite_applied",
            question_raw=question[:120],
            question_retrieval=retrieval_question[:120],
            strategy=rewrite_meta.get("strategy"),
            follow_up=rewrite_meta.get("follow_up"),
        )
        return retrieval_question, compressed, chat_history, rewrite_meta

    async def _lookup_validated_qa_cache(
        self,
        db: AsyncSession,
        *,
        factory_id: str | None,
        question: str,
        principal: Principal | None,
        machine_id: str | None,
        doc_type: str | None,
        allowed_doc_ids: list[str] | None,
    ) -> dict[str, Any] | None:
        from spark.services.qa_cache_service import qa_cache_service
        from spark.services.qa_cache_validator import revalidate_cache_hit

        cached = await qa_cache_service.lookup(
            db,
            factory_id=factory_id,
            question=question,
            principal=principal,
            machine_id=machine_id,
            doc_type=doc_type,
        )
        if cached is None:
            from spark.services.semantic_cache import semantic_cache_lookup
            cached = await semantic_cache_lookup(
                db,
                factory_id=factory_id,
                question=question,
                principal=principal,
                machine_id=machine_id,
            )
        if cached is None:
            return None

        source_doc_ids = [
            uuid.UUID(str(item))
            for item in (cached.get("source_doc_ids") or [])
        ]
        valid = await revalidate_cache_hit(
            db,
            cache_id=str(cached["cache_id"]),
            factory_id=str(factory_id),
            sources=list(cached.get("sources") or []),
            source_doc_ids=source_doc_ids,
            principal=principal,
            allowed_doc_ids=allowed_doc_ids,
            expected_fingerprint=str(cached.get("cache_fingerprint") or ""),
            stored_fingerprint=cached.get("filter_fingerprint"),
        )
        if not valid:
            return None
        return cached

    async def _compress_for_retrieval(self, question: str) -> tuple[str, str | None]:
        from spark.services.query_compression import maybe_compress_question

        return await maybe_compress_question(question)

    def _contextualize_question(
        self,
        question: str,
        routing: QuestionRouting,
        rf: RAGFilter,
        prior_messages: list[ChatMessage],
    ) -> str:
        from spark.retrieval.preprocess.contextualize import (
            contextualize_question,
            source_labels_from_sources,
        )

        last_user = next((m for m in reversed(prior_messages) if m.role == "user"), None)
        last_assistant = next(
            (m for m in reversed(prior_messages) if m.role == "assistant"),
            None,
        )
        return contextualize_question(
            question,
            is_followup=routing.is_followup,
            rf=rf,
            prior_user_content=last_user.content if last_user else None,
            prior_user_contents=self._prior_user_contents(prior_messages),
            source_labels=source_labels_from_sources(
                last_assistant.sources if last_assistant else None
            ),
        )

    def _source_labels(self, sources: list[dict[str, Any]] | None) -> list[str]:
        labels: list[str] = []
        for source in sources or []:
            name = source.get("source_file") or source.get("title") or source.get("doc_id")
            if not name:
                continue
            if source.get("page") is not None:
                labels.append(f"{name} หน้า {source['page']}")
            elif source.get("source_sheet") and source.get("row_number") is not None:
                labels.append(f"{name} sheet {source['source_sheet']} row {source['row_number']}")
            elif source.get("source_sheet"):
                labels.append(f"{name} sheet {source['source_sheet']}")
            else:
                labels.append(str(name))
        return labels

    def _with_effective_question(
        self, used: dict[str, Any], original_question: str, effective_question: str
    ) -> dict[str, Any]:
        if effective_question == original_question:
            return used
        return {**used, "effective_question": effective_question}

    async def _record_audit(
        self,
        db: AsyncSession,
        *,
        principal: Principal | None,
        factory_id: str | None,
        question: str,
        route: str,
        sources: list[dict[str, Any]] | None,
    ) -> None:
        try:
            import uuid as _uuid

            from spark.services.audit_retrieval_service import audit_retrieval_service

            user_uuid: _uuid.UUID | None = None
            if principal and principal.user_id:
                try:
                    user_uuid = _uuid.UUID(str(principal.user_id))
                except ValueError:
                    user_uuid = None
            await audit_retrieval_service.record(
                db,
                user_id=user_uuid,
                factory_id=factory_id,
                question=question,
                route=route,
                sources=sources,
            )
        except Exception as exc:
            log.debug("audit_retrieval_skip", error=str(exc)[:120])

    def _log_chat_answer(
        self,
        *,
        intent: str,
        answer_path: str,
        retrieval_sources: list[str],
        latency_start: float,
        source_count: int,
        question: str,
    ) -> None:
        log.info(
            "chat_answer_produced",
            intent=intent,
            answer_path=answer_path,
            retrieval_sources=retrieval_sources,
            source_count=source_count,
            latency_ms=round((time.perf_counter() - latency_start) * 1000, 2),
            question=question[:120],
        )

    def _merge_filter(self, context: dict | None, req_filter) -> RAGFilter:
        from spark.services.session_slots import merge_session_slots

        _, rf = merge_session_slots(context, req_filter)
        return rf

    def _update_session_context(
        self,
        session_obj: ChatSession,
        rf: RAGFilter,
        *,
        locked_machine_id: str | None = None,
    ) -> None:
        ctx = dict(session_obj.context or {})
        # component scope removed (machines only bind documents) — also purge
        # stale values persisted by older sessions so they stop narrowing RAG.
        ctx.pop("component_id", None)
        for key in ("factory_id", "machine_id", "document_type", "document_category"):
            value = getattr(rf, key, None)
            if value is not None:
                ctx[key] = value
        if locked_machine_id:
            ctx["confirmed_machine_id"] = locked_machine_id
        session_obj.context = ctx


chat_orchestrator = ChatOrchestrator()
