"""Load versioned intent weight tables from YAML (remediation v2 Phase 9)."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

_DEFAULT_PATH = Path(__file__).resolve().parents[4] / "configs" / "retrieval" / "intent_weights_v2.yaml"


@dataclass(frozen=True)
class IntentWeightSpec:
    dense_weight: float
    lexical_weight: float
    document_type_hint: str | None = None
    min_rerank_score: float | None = None
    min_rerank_avg: float | None = None
    min_raw_fusion: float | None = None
    strict_document_type_filter: bool = False


@dataclass(frozen=True)
class IntentWeightsConfig:
    version: int
    abstain_threshold: float
    defaults: IntentWeightSpec
    intents: dict[str, IntentWeightSpec]

    def for_intent(self, intent: str | object) -> IntentWeightSpec:
        key = intent.value if hasattr(intent, "value") else str(intent)
        spec = self.intents.get(key)
        if spec is not None:
            return spec
        return self.defaults


def _coerce_spec(raw: dict[str, Any] | None, *, fallback: IntentWeightSpec) -> IntentWeightSpec:
    if not raw:
        return fallback
    dense = float(raw.get("dense_weight", fallback.dense_weight))
    lexical = float(raw.get("lexical_weight", fallback.lexical_weight))
    hint = raw.get("document_type_hint")
    min_score = raw.get("min_rerank_score")
    min_avg = raw.get("min_rerank_avg")
    min_raw = raw.get("min_raw_fusion")
    return IntentWeightSpec(
        dense_weight=dense,
        lexical_weight=lexical,
        document_type_hint=str(hint).strip() if hint else None,
        min_rerank_score=float(min_score) if min_score is not None else None,
        min_rerank_avg=float(min_avg) if min_avg is not None else None,
        min_raw_fusion=float(min_raw) if min_raw is not None else None,
        strict_document_type_filter=bool(raw.get("strict_document_type_filter", False)),
    )


@lru_cache(maxsize=1)
def load_intent_weights_config(path: str | None = None) -> IntentWeightsConfig:
    cfg_path = Path(path) if path else _DEFAULT_PATH
    raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    defaults_raw = raw.get("defaults") or {}
    default_spec = IntentWeightSpec(
        dense_weight=float(defaults_raw.get("dense_weight", 0.7)),
        lexical_weight=float(defaults_raw.get("lexical_weight", 0.3)),
        min_rerank_score=float(defaults_raw.get("min_rerank_score", 0.35)),
        min_rerank_avg=float(defaults_raw.get("min_rerank_avg", 0.25)),
        min_raw_fusion=float(defaults_raw.get("min_raw_fusion", 0.18)),
    )
    intents_raw = raw.get("intents") or {}
    intents: dict[str, IntentWeightSpec] = {}
    for name, spec_raw in intents_raw.items():
        if not isinstance(spec_raw, dict):
            continue
        intents[str(name)] = _coerce_spec(spec_raw, fallback=default_spec)
    if "general" not in intents:
        intents["general"] = default_spec
    return IntentWeightsConfig(
        version=int(raw.get("version") or 2),
        abstain_threshold=float(raw.get("abstain_threshold") or 0.38),
        defaults=default_spec,
        intents=intents,
    )
