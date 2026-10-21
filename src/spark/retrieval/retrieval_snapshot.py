"""Retrieval audit snapshot builder for compliance replay (Phase 11)."""

from __future__ import annotations

from typing import Any

from .models import RetrievedDoc


def build_retrieval_snapshot(
    *,
    question_raw: str | None,
    question_retrieval: str,
    question_synthesis: str,
    fallback_level: int,
    docs: list[RetrievedDoc],
    fusion_method: str = "rrf",
    rewrite_meta: dict[str, Any] | None = None,
    intent: str | None = None,
    session_slots: dict[str, Any] | None = None,
    retrieval_report: dict[str, Any] | None = None,
    intent_plan: dict[str, Any] | None = None,
    intent_weight_version: int | str | None = None,
    cache_hit: bool = False,
    cache_fingerprint: str | None = None,
    session_slots_hash: str | None = None,
    rewrite_verdict: str | None = None,
) -> dict[str, Any]:
    chunk_ids: list[str] = []
    scores: list[float] = []
    ingest_generations: dict[str, int] = {}

    for doc in docs:
        chunk_id = doc.payload.get("chunk_id")
        if chunk_id:
            chunk_ids.append(str(chunk_id))
            scores.append(round(float(doc.score), 4))
        doc_id = doc.payload.get("doc_id")
        generation = doc.payload.get("ingest_generation")
        if doc_id and generation is not None:
            ingest_generations[str(doc_id)] = int(generation)

    rewrite = dict(rewrite_meta or {})
    rewrite_strategy = rewrite.get("strategy")

    snapshot: dict[str, Any] = {
        "question_retrieval": question_retrieval,
        "question_synthesis": question_synthesis,
        "fallback_level": int(fallback_level),
        "chunk_ids": chunk_ids,
        "scores": scores,
        "fusion_method": fusion_method,
        "ingest_generations": ingest_generations,
    }
    if intent:
        snapshot["intent"] = intent
    if intent_weight_version is not None:
        snapshot["intent_weight_version"] = str(intent_weight_version)
    if intent_plan:
        snapshot["intent_plan"] = intent_plan
    if question_raw:
        snapshot["question_raw"] = question_raw
    if rewrite_meta:
        snapshot["rewrite"] = rewrite_meta
    if rewrite_strategy:
        snapshot["rewrite_strategy"] = rewrite_strategy
    if session_slots:
        snapshot["session_slots"] = session_slots
    if retrieval_report:
        snapshot["retrieval_report"] = retrieval_report
    if cache_hit:
        snapshot["cache_hit"] = True
    if cache_fingerprint:
        snapshot["cache_fingerprint"] = cache_fingerprint
    if session_slots_hash:
        snapshot["session_slots_hash"] = session_slots_hash
    if rewrite_verdict:
        snapshot["rewrite_verdict"] = rewrite_verdict
    return snapshot
