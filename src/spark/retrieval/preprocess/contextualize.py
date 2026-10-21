"""Synthesis question contextualization for generation (Phase 11)."""

from __future__ import annotations

from typing import Any

from spark.retrieval.models import RAGFilter


_MAX_PRIOR_TURNS = 3


def contextualize_question(
    question: str,
    *,
    is_followup: bool,
    rf: RAGFilter,
    prior_user_content: str | None = None,
    prior_user_contents: list[str] | None = None,
    source_labels: list[str] | None = None,
) -> str:
    if not is_followup:
        return question

    context_parts: list[str] = []
    if rf.factory_id:
        context_parts.append(f"factory_id: {rf.factory_id}")
    if rf.machine_id:
        context_parts.append(f"machine_id: {rf.machine_id}")
    if rf.document_type:
        context_parts.append(f"document_type: {rf.document_type}")
    if rf.revision:
        context_parts.append(f"revision: {rf.revision}")

    # A follow-up can reference any recent turn, not just the immediately
    # previous one ("แล้วคำถามแรกล่ะ", "the one before that") — include the last
    # few user turns oldest-first so an n-2 back-reference stays resolvable.
    turns: list[str] = []
    if prior_user_contents:
        turns = [t.strip() for t in prior_user_contents if t and t.strip()]
        turns = turns[-_MAX_PRIOR_TURNS:]
    elif prior_user_content:
        turns = [prior_user_content]
    if len(turns) == 1:
        context_parts.append(f"คำถามก่อนหน้า: {turns[0][:500]}")
    elif turns:
        per_turn_budget = max(120, 600 // len(turns))
        for idx, turn in enumerate(turns, start=1):
            context_parts.append(f"คำถามก่อนหน้า ({idx}): {turn[:per_turn_budget]}")
    if source_labels:
        context_parts.append(f"แหล่งอ้างอิงก่อนหน้า: {', '.join(source_labels[:4])}")

    if not context_parts:
        return question
    return "\n".join([*context_parts, f"คำถามต่อเนื่อง: {question}"])


def source_labels_from_sources(sources: list[dict[str, Any]] | None) -> list[str]:
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
