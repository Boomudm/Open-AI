"""Load intent-aware rerank gate thresholds from YAML."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

from spark.retrieval.intent.router import QueryIntent

_DEFAULT_PATH = Path(__file__).resolve().parents[4] / "configs" / "retrieval" / "rerank_gates.yaml"


@dataclass(frozen=True)
class GateThresholds:
    max: float
    avg: float


@dataclass(frozen=True)
class RerankGatesConfig:
    intents: dict[str, GateThresholds]

    def for_intent(self, intent: QueryIntent | str) -> GateThresholds:
        key = intent.value if isinstance(intent, QueryIntent) else str(intent)
        if key == QueryIntent.UNKNOWN.value:
            key = QueryIntent.GENERAL.value
        return self.intents.get(key, self.intents["general"])


def forge_gates_active() -> bool:
    """True when the Forge-tuned gate file should drive thresholds.

    Mirrors the scoring precedence in cross_encoder.score_pairs: the GPU
    sidecar (bge-reranker) outranks Forge, so the Forge-tuned gates apply
    only when Forge would actually produce the scores being gated.
    """
    from spark.core.forge_client import forge_rerank_active
    from spark.core.gpu_sidecar import sidecar_enabled

    return forge_rerank_active() and not sidecar_enabled()


@lru_cache(maxsize=1)
def load_rerank_gates_config(path: str | None = None) -> RerankGatesConfig:
    if path is None:
        from spark.core.config import settings

        if forge_gates_active():
            forge_path = (settings.forge_rerank_gates_path or "").strip()
            if forge_path:
                path = forge_path
            else:
                default_forge = _DEFAULT_PATH.parent / "rerank_gates_forge.yaml"
                if default_forge.is_file():
                    path = str(default_forge)
    cfg_path = Path(path) if path else _DEFAULT_PATH
    raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    intents_raw = raw.get("intents") or {}
    intents: dict[str, GateThresholds] = {}
    for name, spec in intents_raw.items():
        if not isinstance(spec, dict):
            continue
        intents[name] = GateThresholds(
            max=float(spec.get("min_max", 0.35)),
            avg=float(spec.get("min_avg", 0.25)),
        )
    if "general" not in intents:
        intents["general"] = GateThresholds(max=0.35, avg=0.25)
    return RerankGatesConfig(intents=intents)


def thresholds_for_intent(
    intent: QueryIntent | str | None,
    *,
    tuning_max: float | None = None,
    tuning_avg: float | None = None,
) -> GateThresholds:
    cfg = load_rerank_gates_config()
    if intent is not None:
        base = cfg.for_intent(intent)
    else:
        base = cfg.for_intent(QueryIntent.GENERAL)
    if tuning_max is not None or tuning_avg is not None:
        return GateThresholds(
            max=tuning_max if tuning_max is not None else base.max,
            avg=tuning_avg if tuning_avg is not None else base.avg,
        )
    return base
