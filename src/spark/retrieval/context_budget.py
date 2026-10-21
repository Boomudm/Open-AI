"""Token budget helpers for RAG and multi-turn chat context assembly."""

from __future__ import annotations

from dataclasses import dataclass

from spark.core.config import settings
from spark.core.llm_profile import load_llm_profile
from spark.core.logging import get_logger

from .models import RetrievedDoc
from spark.generation.parent_context import generation_context_for_doc
from spark.generation.prompts import HUMAN_PROMPT, SYSTEM_PROMPT

log = get_logger(__name__)

_CHARS_PER_TOKEN_FALLBACK = 2.5
_MIN_DOC_BUDGET_TOKENS = 512


@dataclass(frozen=True)
class ContextBudget:
    max_context_tokens: int
    reserved_output_tokens: int
    system_overhead_tokens: int
    question_tokens: int

    @property
    def doc_budget_tokens(self) -> int:
        remaining = (
            self.max_context_tokens
            - self.reserved_output_tokens
            - self.system_overhead_tokens
            - self.question_tokens
            - settings.context_safety_margin_tokens
        )
        return max(_MIN_DOC_BUDGET_TOKENS, remaining)

    @property
    def history_budget_tokens(self) -> int:
        """Tokens available for chat history after reserving docs + question."""
        return max(
            0,
            self.max_context_tokens
            - self.reserved_output_tokens
            - self.system_overhead_tokens
            - self.question_tokens
            - settings.context_safety_margin_tokens
            - _MIN_DOC_BUDGET_TOKENS,
        )


@dataclass(frozen=True)
class DocTrimResult:
    docs: list[RetrievedDoc]
    trimmed_chunks: int
    reason: str
    doc_budget_tokens: int
    used_tokens: int


def count_tokens(text: str, model: str | None = None) -> int:
    """Estimate token count via configured TokenCounter backend."""
    from spark.retrieval.token_counter import get_token_counter

    return get_token_counter().count(text, model)


def _rag_system_overhead_tokens(model: str | None = None) -> int:
    template = SYSTEM_PROMPT.replace("{context}", "") + HUMAN_PROMPT.replace("{question}", "")
    return count_tokens(template, model)


def build_rag_context_budget(question: str, *, model: str | None = None) -> ContextBudget:
    profile = load_llm_profile()
    llm_model = model or str(profile.get("llm_model") or settings.ollama_llm_model)
    max_ctx = int(profile.get("num_ctx", settings.ollama_llm_num_ctx))
    reserved_output = int(
        profile.get("max_tokens", settings.context_reserved_output_tokens)
    )
    return ContextBudget(
        max_context_tokens=max_ctx,
        reserved_output_tokens=reserved_output,
        system_overhead_tokens=_rag_system_overhead_tokens(llm_model),
        question_tokens=count_tokens(question, llm_model),
    )


def _doc_chunk_tokens(doc: RetrievedDoc, model: str | None) -> int:
    payload = doc.payload
    locator = f"หน้า {payload.get('page')}" if payload.get("page") is not None else ""
    if not locator and payload.get("source_sheet"):
        locator = f"sheet {payload.get('source_sheet')}"
        if payload.get("row_number") is not None:
            locator = f"{locator} row {payload.get('row_number')}"
    label = (
        f"[{payload.get('source_file', '?')} {locator or '-'} | "
        f"{payload.get('document_type', '')}]"
    )
    return count_tokens(f"{label}\n{generation_context_for_doc(doc)}", model)


def fit_docs_to_budget(
    docs: list[RetrievedDoc],
    budget_tokens: int,
    *,
    model: str | None = None,
) -> DocTrimResult:
    """Keep highest-score chunks first; drop or truncate lowest-score chunks to fit budget."""
    if not docs or budget_tokens <= 0:
        return DocTrimResult(
            docs=[],
            trimmed_chunks=len(docs),
            reason="empty_budget",
            doc_budget_tokens=budget_tokens,
            used_tokens=0,
        )

    kept: list[RetrievedDoc] = []
    used = 0
    trimmed = 0

    for doc in docs:
        chunk_tokens = _doc_chunk_tokens(doc, model)
        if used + chunk_tokens <= budget_tokens:
            kept.append(doc)
            used += chunk_tokens
            continue

        remaining = budget_tokens - used
        if remaining < 64:
            trimmed += 1
            continue

        truncated_content = _truncate_doc_content(doc, remaining, model)
        if truncated_content:
            payload = dict(doc.payload)
            kept.append(
                RetrievedDoc(
                    page_content=truncated_content,
                    score=doc.score,
                    vector_score=doc.vector_score,
                    payload=payload,
                )
            )
            used += _doc_chunk_tokens(kept[-1], model)
        trimmed += 1

    reason = "none"
    if trimmed:
        reason = "low_score_chunks" if kept else "budget_exceeded"

    return DocTrimResult(
        docs=kept,
        trimmed_chunks=trimmed,
        reason=reason,
        doc_budget_tokens=budget_tokens,
        used_tokens=used,
    )


def _truncate_doc_content(
    doc: RetrievedDoc, max_tokens: int, model: str | None
) -> str | None:
    payload = doc.payload
    locator = f"หน้า {payload.get('page')}" if payload.get("page") is not None else ""
    label = f"[{payload.get('source_file', '?')} {locator or '-'} | {payload.get('document_type', '')}]"
    label_tokens = count_tokens(f"{label}\n", model)
    content_budget = max_tokens - label_tokens - 8
    if content_budget < 32:
        return None

    content = generation_context_for_doc(doc)
    low, high = 0, len(content)
    best = ""
    while low <= high:
        mid = (low + high) // 2
        candidate = content[:mid]
        if count_tokens(candidate, model) <= content_budget:
            best = candidate
            low = mid + 1
        else:
            high = mid - 1
    return best.rstrip() if best else None


@dataclass(frozen=True)
class ChatMessageSlice:
    role: str
    content: str


def fit_messages_to_budget(
    messages: list[ChatMessageSlice],
    budget_tokens: int,
    *,
    model: str | None = None,
) -> list[ChatMessageSlice]:
    """Keep most recent messages that fit within budget (newest first)."""
    if budget_tokens <= 0 or not messages:
        return []

    kept: list[ChatMessageSlice] = []
    used = 0
    for msg in reversed(messages):
        msg_tokens = count_tokens(msg.content, model) + 4
        if used + msg_tokens > budget_tokens:
            break
        kept.insert(0, msg)
        used += msg_tokens
    return kept


def log_context_budget_applied(
    *,
    question: str,
    budget: ContextBudget,
    trim: DocTrimResult,
) -> None:
    log.info(
        "context_budget_applied",
        question=question[:120],
        max_context_tokens=budget.max_context_tokens,
        doc_budget_tokens=trim.doc_budget_tokens,
        doc_tokens_used=trim.used_tokens,
        trimmed_chunks=trim.trimmed_chunks,
        trim_reason=trim.reason,
    )
