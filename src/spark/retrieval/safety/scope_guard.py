"""Machine scope guards for retrieval (Phase 9)."""

from __future__ import annotations

from spark.retrieval.models import RAGFilter, RetrievedDoc
from spark.retrieval.scoring import (
    _filter_machine_conflicts,
    _machine_anchors,
    _machine_ids_in_text,
    should_refuse_rag_answer,
)

__all__ = [
    "_filter_machine_conflicts",
    "_machine_anchors",
    "_machine_ids_in_text",
    "should_refuse_rag_answer",
    "filter_machine_conflicts",
    "question_machine_anchors",
]


def filter_machine_conflicts(
    question: str,
    rf: RAGFilter,
    docs: list[RetrievedDoc],
    *,
    known_factory_machines: set[str] | None = None,
) -> list[RetrievedDoc]:
    return _filter_machine_conflicts(
        question,
        rf,
        docs,
        known_factory_machines=known_factory_machines,
    )


def question_machine_anchors(question: str, rf: RAGFilter) -> set[str]:
    return _machine_anchors(question, rf)
