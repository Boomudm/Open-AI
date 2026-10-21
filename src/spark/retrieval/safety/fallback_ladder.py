"""Scope-safe fallback ladder v3 — no level 4; safety intent blocks broadening (Phase 9)."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Awaitable, Callable

from spark.retrieval.safety.safety_intent import SafetyIntent, SafetyIntentKind, detect_safety_intent
from spark.generation.context import is_machine_anchored
from spark.retrieval.models import RAGFilter, RetrievedDoc
from spark.retrieval.scoring import _machine_ids_in_text, _should_keep_document_type_filter


@dataclass(frozen=True)
class FallbackContext:
    question: str
    rf: RAGFilter
    allow_scope_broadening: bool = False
    safety_intent: SafetyIntent | None = None


def question_has_machine_anchor_tokens(question: str) -> bool:
    return bool(_machine_ids_in_text(question))


def can_broaden_machine_scope(ctx: FallbackContext) -> bool:
    if question_has_machine_anchor_tokens(ctx.question):
        return False
    if ctx.allow_scope_broadening:
        return True
    return not is_machine_anchored(ctx.rf)


def _resolve_safety_intent(ctx: FallbackContext) -> SafetyIntent:
    if ctx.safety_intent is not None:
        return ctx.safety_intent
    return detect_safety_intent(ctx.question)


def build_fallback_levels(ctx: FallbackContext) -> list[tuple[int, RAGFilter]]:
    rf = ctx.rf
    levels: list[tuple[int, RAGFilter]] = [(0, rf)]

    safety = _resolve_safety_intent(ctx)
    if safety.kind != SafetyIntentKind.NONE:
        return levels

    if rf.document_type and not _should_keep_document_type_filter(ctx.question, rf):
        levels.append((1, RAGFilter(**{**asdict(rf), "document_type": None})))

    # (level 2 — component broadening — removed: retrieval no longer scopes by
    # component; machines exist only to bind documents.)

    if rf.machine_id and can_broaden_machine_scope(ctx):
        levels.append(
            (
                3,
                RAGFilter(
                    factory_id=rf.factory_id,
                    language=rf.language,
                    only_active=rf.only_active,
                    latest_revision_only=rf.latest_revision_only,
                ),
            )
        )

    return levels


async def run_fallback_ladder(
    ctx: FallbackContext,
    *,
    retrieve: Callable[[RAGFilter], Awaitable[list[RetrievedDoc]]],
    candidate_ok: Callable[[list[RetrievedDoc]], bool],
    latest_revision_only: bool,
    filter_latest: Callable[[list[RetrievedDoc]], list[RetrievedDoc]],
    rerank_degraded: bool = False,
    rerank_policy: str = "ce_active",
) -> tuple[list[RetrievedDoc], int, RAGFilter]:
    from spark.retrieval.degraded_policy import DegradedRetrievalPolicy

    docs: list[RetrievedDoc] = []
    fallback_level = 0
    active_rf = ctx.rf
    safety = _resolve_safety_intent(ctx)
    if (
        safety.kind != SafetyIntentKind.NONE
        and rerank_degraded
        and rerank_policy == DegradedRetrievalPolicy.CE_TIMEOUT_ABSTAIN.value
    ):
        return docs, fallback_level, active_rf

    for level, level_rf in build_fallback_levels(ctx):
        docs = await retrieve(level_rf)
        if latest_revision_only:
            docs = filter_latest(docs)
        fallback_level = level
        active_rf = level_rf
        if candidate_ok(docs):
            return docs, fallback_level, active_rf
    return docs, fallback_level, active_rf
