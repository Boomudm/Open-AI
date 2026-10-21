"""Load degraded-mode fusion rank/floor thresholds (Phase 7)."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

from spark.retrieval.intent.router import QueryIntent

_DEFAULT_PATH = (
    Path(__file__).resolve().parents[3] / "configs" / "retrieval" / "degraded_fusion_floors.yaml"
)


@dataclass(frozen=True)
class DegradedFusionFloor:
    min_raw_fusion: float
    max_fusion_rank: int
    min_rank_gap: float


@dataclass(frozen=True)
class DegradedFusionFloorsConfig:
    intents: dict[str, DegradedFusionFloor]
    safety_abstain_raw_fusion: float
    default_max_fusion_rank: int
    default_min_rank_gap: float

    def for_intent(self, intent: QueryIntent | str) -> DegradedFusionFloor:
        key = intent.value if isinstance(intent, QueryIntent) else str(intent)
        if key == QueryIntent.UNKNOWN.value:
            key = QueryIntent.GENERAL.value
        return self.intents.get(key, self.intents["general"])


@lru_cache(maxsize=1)
def load_degraded_fusion_floors(path: str | None = None) -> DegradedFusionFloorsConfig:
    cfg_path = Path(path) if path else _DEFAULT_PATH
    raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    defaults = raw.get("defaults") or {}
    max_rank = int(defaults.get("max_fusion_rank", 3))
    min_gap = float(defaults.get("min_rank_gap", 0.04))
    safety = raw.get("safety") or {}
    abstain = float(safety.get("abstain_raw_fusion", 0.28))

    intents: dict[str, DegradedFusionFloor] = {}
    for name, spec in (raw.get("intents") or {}).items():
        if not isinstance(spec, dict):
            continue
        intents[name] = DegradedFusionFloor(
            min_raw_fusion=float(spec.get("min_raw_fusion", 0.18)),
            max_fusion_rank=int(spec.get("max_fusion_rank", max_rank)),
            min_rank_gap=float(spec.get("min_rank_gap", min_gap)),
        )
    if "general" not in intents:
        intents["general"] = DegradedFusionFloor(
            min_raw_fusion=0.18,
            max_fusion_rank=max_rank,
            min_rank_gap=min_gap,
        )
    return DegradedFusionFloorsConfig(
        intents=intents,
        safety_abstain_raw_fusion=abstain,
        default_max_fusion_rank=max_rank,
        default_min_rank_gap=min_gap,
    )
