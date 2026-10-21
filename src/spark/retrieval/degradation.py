"""Retrieval degradation report — surfaced in RAG API responses (Phase 7)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RetrievalReport:
    degraded: bool = False
    degraded_reasons: list[str] = field(default_factory=list)
    failed_collections: list[str] = field(default_factory=list)
    vector_count: int = 0
    lexical_count: int = 0
    fusion_method: str = "weighted_rrf"
    intent: str = "general"
    sparse_encoder_id: str = ""
    sparse_available: bool = True
    rerank_degraded: bool = False
    rerank_degraded_policy: str = "ce_active"

    def to_dict(self) -> dict:
        return {
            "degraded": self.degraded,
            "degraded_reasons": list(self.degraded_reasons),
            "failed_collections": list(self.failed_collections),
            "vector_count": self.vector_count,
            "lexical_count": self.lexical_count,
            "fusion_method": self.fusion_method,
            "intent": self.intent,
            "sparse_encoder_id": self.sparse_encoder_id,
            "sparse_available": self.sparse_available,
            "rerank_degraded": self.rerank_degraded,
            "rerank_degraded_policy": self.rerank_degraded_policy,
        }


def build_retrieval_report(
    *,
    intent: str,
    fusion_method: str,
    vector_count: int,
    lexical_count: int,
    failed_collections: list[str],
    embed_failed: bool = False,
    lexical_failed: bool = False,
    sparse_encoder_id: str = "",
    rerank_degraded: bool = False,
    rerank_degraded_policy: str = "ce_active",
) -> RetrievalReport:
    reasons: list[str] = []
    for coll in failed_collections:
        reasons.append(f"vector_collection_failed:{coll}")
    if embed_failed:
        reasons.append("embed_failed")
    if lexical_failed:
        reasons.append("lexical_failed")
    if rerank_degraded:
        reasons.append("rerank_ce_unavailable")

    sparse_available = bool(sparse_encoder_id and sparse_encoder_id != "none" and not embed_failed)

    degraded = bool(reasons) or (
        vector_count == 0 and lexical_count > 0 and failed_collections
    ) or (lexical_failed and vector_count > 0)

    return RetrievalReport(
        degraded=degraded,
        degraded_reasons=reasons,
        failed_collections=list(failed_collections),
        vector_count=vector_count,
        lexical_count=lexical_count,
        fusion_method=fusion_method,
        intent=intent,
        sparse_encoder_id=sparse_encoder_id,
        sparse_available=sparse_available,
        rerank_degraded=rerank_degraded,
        rerank_degraded_policy=rerank_degraded_policy,
    )
