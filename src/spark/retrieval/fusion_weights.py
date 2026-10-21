"""Hybrid fusion weight resolution — intent plan × factory config (Phase 9)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from spark.retrieval.tuning import RagFusionConfig

_POLICY_PATH = (
    Path(__file__).resolve().parents[3] / "configs" / "retrieval" / "sparse_weight_policy.yaml"
)


def resolve_hybrid_weights(
    intent_dense: float,
    intent_lexical: float,
    fusion_cfg: RagFusionConfig,
) -> tuple[float, float]:
    """Normalized product of intent router and factory fusion weights."""
    dense = max(0.0, float(intent_dense)) * max(0.0, float(fusion_cfg.dense_weight))
    lexical = max(0.0, float(intent_lexical)) * max(0.0, float(fusion_cfg.lexical_weight))
    total = dense + lexical
    if total <= 0:
        return 0.7, 0.3
    return dense / total, lexical / total


@lru_cache(maxsize=1)
def load_sparse_weight_policy(path: str | None = None) -> dict[str, Any]:
    cfg_path = Path(path) if path else _POLICY_PATH
    raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    return raw if isinstance(raw, dict) else {}


def sparse_leg_snapshot(*, sparse_encoder_id: str | None) -> dict[str, Any]:
    """Return sparse leg metadata for retrieval feature logs."""
    policy = load_sparse_weight_policy()
    active = bool(sparse_encoder_id and str(sparse_encoder_id).strip().lower() not in {"", "none"})
    weight = float(policy.get("default_sparse_weight") or 0.0) if active else 0.0
    return {
        "sparse_encoder_id": sparse_encoder_id or "none",
        "sparse_leg_active": active,
        "sparse_leg_weight": weight,
        "log_sparse_contribution": bool(policy.get("log_sparse_contribution", True)),
        "future_tri_leg_fusion": bool(policy.get("future_tri_leg_fusion", True)),
    }
