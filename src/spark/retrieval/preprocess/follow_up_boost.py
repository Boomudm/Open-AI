"""Grounded follow-up retrieval boost for prior chunk memory (Phase 11)."""

from __future__ import annotations

from spark.retrieval.models import RetrievedDoc

_FOLLOW_UP_SCORE_BOOST = 0.08
_SAME_SECTION_MARKERS = (
    "same section",
    "section เดิม",
    "ส่วนเดิม",
    "หัวข้อเดิม",
    "same chunk",
)


def user_requests_same_section_only(question: str) -> bool:
    lower = (question or "").lower()
    return any(marker in lower for marker in _SAME_SECTION_MARKERS)


def boost_follow_up_chunks(
    docs: list[RetrievedDoc],
    *,
    chunk_ids: list[str] | None,
    follow_up: bool,
    question: str,
    evidence_age_turns: int | None = None,
    evidence_turn_ttl: int = 3,
) -> list[RetrievedDoc]:
    """Boost prior chunks in fused results without narrowing retrieval scope."""
    if not follow_up or not chunk_ids or user_requests_same_section_only(question):
        return docs
    if evidence_age_turns is not None and evidence_age_turns > evidence_turn_ttl:
        return docs

    wanted = {str(chunk_id).lower() for chunk_id in chunk_ids if chunk_id}
    if not wanted:
        return docs

    boosted: list[RetrievedDoc] = []
    for doc in docs:
        chunk_id = str(doc.payload.get("chunk_id") or "").lower()
        if chunk_id not in wanted:
            boosted.append(doc)
            continue
        score = float(doc.fusion_score or doc.score or 0.0)
        score = min(1.0, score + _FOLLOW_UP_SCORE_BOOST)
        boosted.append(
            RetrievedDoc(
                page_content=doc.page_content,
                score=score,
                vector_score=doc.vector_score,
                payload=doc.payload,
                lexical_score=doc.lexical_score,
                fusion_score=score,
            )
        )
    return sorted(boosted, key=lambda item: float(item.fusion_score or item.score or 0.0), reverse=True)
