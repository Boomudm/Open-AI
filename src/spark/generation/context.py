"""Grounded context assembly for LLM generation (Phase 10).

Remediation v4: chat history sanitization against prompt injection.
"""

from __future__ import annotations

import re
from typing import Any

from spark.core.logging import get_logger
from spark.generation.parent_context import doc_chunk_id, group_docs_for_generation
from spark.retrieval.models import RAGFilter, RetrievedDoc
from spark.retrieval.synthesis import _source_label

log = get_logger(__name__)


def is_machine_anchored(scope_rf: Any) -> bool:
    return bool(getattr(scope_rf, "machine_id", None))


def build_grounded_context(docs: list[RetrievedDoc]) -> str:
    parts: list[str] = []
    for group, context_text in group_docs_for_generation(docs):
        chunk_tags = ", ".join(
            f"chunk_id:{doc_chunk_id(doc)}" for doc in group if doc_chunk_id(doc)
        )
        if not chunk_tags:
            continue
        anchor = group[0]
        p = anchor.payload
        locator = f"หน้า {p.get('page')}" if p.get("page") is not None else ""
        if not locator and p.get("source_sheet"):
            locator = f"sheet {p.get('source_sheet')}"
            if p.get("row_number") is not None:
                locator = f"{locator} row {p.get('row_number')}"
        meta = f"{p.get('source_file', '?')} {locator or '-'} | {p.get('document_type', '')}"
        if any(g.payload.get("needs_review") for g in group):
            meta += " | ตีความจากภาพโดย AI ยังไม่ยืนยันโดยมนุษย์ — ต้องเตือนผู้ใช้ให้ตรวจสอบภาพต้นฉบับก่อนใช้งานจริง"
        parts.append(f"[{chunk_tags}] ({meta})\n{context_text}")
    return "\n\n---\n\n".join(parts)


def chunk_id_map(docs: list[RetrievedDoc]) -> dict[str, RetrievedDoc]:
    mapping: dict[str, RetrievedDoc] = {}
    for doc in docs:
        chunk_id = doc_chunk_id(doc)
        if chunk_id:
            mapping[chunk_id.lower()] = doc
    return mapping


def append_readable_citations(answer: str, cited_docs: list[RetrievedDoc]) -> str:
    labels: list[str] = []
    seen: set[str] = set()
    for doc in cited_docs:
        label = _source_label(doc)
        if label in seen:
            continue
        labels.append(label)
        seen.add(label)
        if len(labels) >= 3:
            break
    if not labels:
        return answer
    if any(label in answer for label in labels):
        return answer
    return f"{answer.rstrip()}\n\nอ้างอิง: {', '.join(labels)}"


_INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?(previous|prior|above)\s+(instructions?|rules?|context)", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+(a|an|in)\s+", re.IGNORECASE),
    re.compile(r"system\s*:\s*", re.IGNORECASE),
    re.compile(r"<\|?(system|assistant|im_start)\|?>", re.IGNORECASE),
    re.compile(r"\[INST\]|\[/INST\]|<<SYS>>|<</SYS>>", re.IGNORECASE),
    re.compile(r"forget\s+(everything|all|your)\s+(above|previous|instructions?)", re.IGNORECASE),
    re.compile(r"(override|bypass|disable)\s+(safety|filter|guard|restriction)", re.IGNORECASE),
    re.compile(r"disregard\s+(safety|lockout|all)", re.IGNORECASE),
    re.compile(r"skip\s+loto", re.IGNORECASE),
]

_MAX_CHAT_MESSAGE_LENGTH = 2000
_MAX_HISTORY_TURNS = 10


def _message_has_injection(content: str) -> bool:
    return any(pat.search(content) for pat in _INJECTION_PATTERNS)


def _sanitize_chat_message(content: str) -> str:
    if not content:
        return ""
    content = content[:_MAX_CHAT_MESSAGE_LENGTH]
    content = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", content)
    content = re.sub(r"<\|?(system|assistant|im_start|im_end)\|?>", "", content, flags=re.IGNORECASE)
    content = re.sub(r"\[INST\]|\[/INST\]|<<SYS>>|<</SYS>>", "", content, flags=re.IGNORECASE)
    return content.strip()


def sanitize_chat_history(
    chat_history: list[tuple[str, str]] | None,
) -> list[tuple[str, str]]:
    """Strip injection patterns and truncate chat history to safe bounds."""
    if not chat_history:
        return []
    sanitized: list[tuple[str, str]] = []
    for role, content in chat_history[-_MAX_HISTORY_TURNS:]:
        cleaned = _sanitize_chat_message(content)
        if _message_has_injection(cleaned):
            log.warning("chat_history_injection_detected", role=role, content_preview=cleaned[:100])
            continue
        if cleaned:
            sanitized.append((role, cleaned))
    return sanitized


def llm_prompt_payload(
    *,
    context: str,
    question: str,
    chat_history: list[tuple[str, str]] | None,
) -> dict[str, Any]:
    from langchain_core.messages import AIMessage, HumanMessage

    safe_history = sanitize_chat_history(chat_history)
    history_messages: list[Any] = []
    for role, content in safe_history:
        if role in ("human", "user"):
            history_messages.append(HumanMessage(content=content))
        else:
            history_messages.append(AIMessage(content=content))
    return {
        "context": context,
        "question": question,
        "history": history_messages,
    }


def machine_filter_from_scope(scope_rf: RAGFilter | None) -> RAGFilter:
    return scope_rf or RAGFilter()
