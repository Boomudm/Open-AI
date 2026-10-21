#!/usr/bin/env python3
"""Verify config keys declared in code have readers (remediation v2 Phase 1)."""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
INGEST_DIR = ROOT / "configs" / "ingestion"
SRC = ROOT / "src" / "spark"

FUSION_READER_MARKERS = (
    "resolve_hybrid_weights",
)


def _load_ingestion_configs() -> list[Path]:
    if not INGEST_DIR.is_dir():
        return []
    return sorted(INGEST_DIR.glob("*.yaml"))


def _ingest_config_keys() -> set[str]:
    keys: set[str] = set()
    for path in _load_ingestion_configs():
        with path.open(encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
        if isinstance(data, dict):
            keys.update(data.keys())
    return keys


def _src_mentions(token: str) -> bool:
    needle = token.lower()
    for path in SRC.rglob("*.py"):
        if needle in path.read_text(encoding="utf-8").lower():
            return True
    return False


def verify_fusion_config_wired() -> list[str]:
    errors: list[str] = []
    core_path = SRC / "retrieval" / "engine.py"
    if not core_path.is_file():
        errors.append("missing retrieval/engine.py")
        return errors
    text = core_path.read_text(encoding="utf-8")
    for marker in FUSION_READER_MARKERS:
        if marker not in text:
            errors.append(f"retrieval/engine.py missing fusion marker: {marker}")
    weights_path = SRC / "retrieval" / "fusion_weights.py"
    if not weights_path.is_file():
        errors.append("missing retrieval/fusion_weights.py")
    return errors


def verify_ingest_top_level_keys() -> list[str]:
    errors: list[str] = []
    optional_unreferenced = {"description", "notes", "optional_metadata"}
    for key in sorted(_ingest_config_keys() - optional_unreferenced):
        if not _src_mentions(key):
            errors.append(f"ingest config key {key!r} has no obvious reader in src/spark")
    return errors


def verify_retrieval_config_sync() -> list[str]:
    errors: list[str] = []
    rerank_path = ROOT / "configs" / "retrieval" / "rerank_gates.yaml"
    floors_path = ROOT / "configs" / "retrieval" / "degraded_fusion_floors.yaml"
    weights_path = ROOT / "configs" / "retrieval" / "intent_weights_v2.yaml"
    for path in (rerank_path, floors_path, weights_path):
        if not path.is_file():
            errors.append(f"missing retrieval config: {path.name}")
            continue
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(data, dict):
            errors.append(f"{path.name} must be a mapping")

    if rerank_path.is_file() and not rerank_path.read_text(encoding="utf-8").startswith(
        "# AUTO-GENERATED from intent_weights_v2.yaml"
    ):
        errors.append("rerank_gates.yaml must be AUTO-GENERATED from intent_weights_v2.yaml")

    if floors_path.is_file() and not floors_path.read_text(encoding="utf-8").startswith(
        "# AUTO-GENERATED from intent_weights_v2.yaml"
    ):
        errors.append("degraded_fusion_floors.yaml must be AUTO-GENERATED from intent_weights_v2.yaml")

    if rerank_path.is_file() and weights_path.is_file():
        rerank = yaml.safe_load(rerank_path.read_text(encoding="utf-8")) or {}
        weights = yaml.safe_load(weights_path.read_text(encoding="utf-8")) or {}
        weight_intents = weights.get("intents") or {}
        defaults = weights.get("defaults") or {}
        for name, gate_spec in (rerank.get("intents") or {}).items():
            src = weight_intents.get(name) or defaults
            expected_max = float(src.get("min_rerank_score", defaults.get("min_rerank_score", 0.35)))
            actual_max = float(gate_spec.get("min_max", 0))
            if round(actual_max, 2) != round(expected_max, 2):
                errors.append(
                    f"rerank_gates.yaml intent {name!r} min_max {actual_max} != "
                    f"intent_weights min_rerank_score {expected_max}"
                )

    if rerank_path.is_file() and floors_path.is_file():
        rerank = yaml.safe_load(rerank_path.read_text(encoding="utf-8")) or {}
        floors = yaml.safe_load(floors_path.read_text(encoding="utf-8")) or {}
        rerank_intents = set((rerank.get("intents") or {}).keys())
        floor_intents = set((floors.get("intents") or {}).keys())
        missing = rerank_intents - floor_intents
        if missing:
            errors.append(
                f"degraded_fusion_floors.yaml missing intents present in rerank_gates.yaml: {sorted(missing)}"
            )

    floors_reader = ROOT / "src" / "spark" / "retrieval" / "degraded_floors_config.py"
    policy_reader = ROOT / "src" / "spark" / "retrieval" / "degraded_policy.py"
    if not floors_reader.is_file():
        errors.append("missing retrieval/degraded_floors_config.py")
    if not policy_reader.is_file():
        errors.append("missing retrieval/degraded_policy.py")
    return errors


def main() -> int:
    errors = (
        verify_fusion_config_wired()
        + verify_ingest_top_level_keys()
        + verify_retrieval_config_sync()
    )
    if errors:
        for err in errors:
            print(f"ERROR: {err}", file=sys.stderr)
        return 1
    print("Config contract verification passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
