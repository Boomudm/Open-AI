"""Per-factory RAG tuning and fusion config resolved from FactoryConfigService."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from spark.core.config import settings
from spark.retrieval.constants import MIN_RERANK_AVG_SCORE, MIN_RERANK_SCORE

FusionMethod = Literal["rrf", "weighted_rrf", "convex"]


@dataclass(frozen=True)
class RagTuningContext:
    top_k_default: int = 6
    # Absolute relevance-gate thresholds on the authoritative [0,1] rerank scale.
    min_max_score: float = MIN_RERANK_SCORE
    min_avg_score: float = MIN_RERANK_AVG_SCORE
    chunk_profile: str | None = None
    fusion_method: str = "rrf"

    @classmethod
    def from_factory_config(cls, config: dict[str, Any]) -> RagTuningContext:
        rag = config.get("rag") or {}
        min_max = rag.get("min_max_score")
        min_avg = rag.get("min_avg_score")
        fusion = RagFusionConfig.from_factory_config(config)
        return cls(
            top_k_default=int(rag.get("top_k_default") or 6),
            min_max_score=float(min_max) if min_max is not None else MIN_RERANK_SCORE,
            min_avg_score=float(min_avg) if min_avg is not None else MIN_RERANK_AVG_SCORE,
            chunk_profile=rag.get("chunk_profile"),
            fusion_method=fusion.method,
        )


@dataclass(frozen=True)
class RagFusionConfig:
    method: FusionMethod = "rrf"
    dense_weight: float = 0.7
    lexical_weight: float = 0.3
    rrf_k: int = 20

    @classmethod
    def from_factory_config(cls, config: dict[str, Any]) -> RagFusionConfig:
        rag = config.get("rag") or {}
        method = str(rag.get("fusion_method") or "rrf").strip().lower()
        if method not in {"rrf", "weighted_rrf", "convex"}:
            method = "rrf"
        dense = float(rag.get("dense_weight", 0.7))
        lexical = float(rag.get("lexical_weight", 0.3))
        rrf_k = int(rag.get("rrf_k") or settings.rag_rrf_k)
        return cls(
            method=method,  # type: ignore[arg-type]
            dense_weight=dense,
            lexical_weight=lexical,
            rrf_k=rrf_k,
        )

    def weights_for_lists(self, list_count: int) -> list[float]:
        base = [self.dense_weight, self.lexical_weight]
        if list_count <= 0:
            return []
        if list_count == 1:
            return [base[0]]
        if list_count >= 2:
            return [base[0], base[1]]
        return base[:list_count]
