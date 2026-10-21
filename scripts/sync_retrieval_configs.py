#!/usr/bin/env python3
"""Generate retrieval YAML artifacts from intent_weights_v2.yaml (Phase 9).

Usage:
  uv run python scripts/sync_retrieval_configs.py          # write files
  uv run python scripts/sync_retrieval_configs.py --check # CI verify only
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WEIGHTS_PATH = ROOT / "configs" / "retrieval" / "intent_weights_v2.yaml"
RERANK_PATH = ROOT / "configs" / "retrieval" / "rerank_gates.yaml"
FLOORS_PATH = ROOT / "configs" / "retrieval" / "degraded_fusion_floors.yaml"

GENERATED_HEADER = (
    "# AUTO-GENERATED from intent_weights_v2.yaml — do not edit by hand.\n"
    "# Regenerate: uv run python scripts/sync_retrieval_configs.py\n"
)


def _load_weights() -> dict:
    return yaml.safe_load(WEIGHTS_PATH.read_text(encoding="utf-8")) or {}


def build_rerank_gates(weights: dict) -> dict:
    defaults = weights.get("defaults") or {}
    intents_out: dict[str, dict[str, float]] = {}
    for name, spec in (weights.get("intents") or {}).items():
        if not isinstance(spec, dict):
            continue
        min_max = float(spec.get("min_rerank_score", defaults.get("min_rerank_score", 0.35)))
        min_avg = float(spec.get("min_rerank_avg", defaults.get("min_rerank_avg", min_max - 0.10)))
        intents_out[str(name)] = {"min_max": round(min_max, 2), "min_avg": round(min_avg, 2)}
    return {"intents": intents_out}


def build_degraded_floors(weights: dict) -> dict:
    defaults = weights.get("defaults") or {}
    safety_loto = (weights.get("intents") or {}).get("safety_loto") or {}
    intents_out: dict[str, dict[str, float]] = {}
    for name, spec in (weights.get("intents") or {}).items():
        if not isinstance(spec, dict):
            continue
        intents_out[str(name)] = {
            "min_raw_fusion": round(
                float(spec.get("min_raw_fusion", defaults.get("min_raw_fusion", 0.18))),
                2,
            )
        }
    return {
        "defaults": {
            "max_fusion_rank": int(defaults.get("max_fusion_rank", 3)),
            "min_rank_gap": float(defaults.get("min_rank_gap", 0.04)),
        },
        "safety": {
            "abstain_raw_fusion": round(
                float(safety_loto.get("min_raw_fusion", 0.28)),
                2,
            )
        },
        "intents": intents_out,
    }


def _render_yaml(payload: dict) -> str:
    body = yaml.safe_dump(payload, sort_keys=False, default_flow_style=False)
    return GENERATED_HEADER + body


def sync(*, check_only: bool = False) -> list[str]:
    errors: list[str] = []
    if not WEIGHTS_PATH.is_file():
        return [f"missing {WEIGHTS_PATH}"]

    weights = _load_weights()
    rerank_expected = _render_yaml(build_rerank_gates(weights))
    floors_expected = _render_yaml(build_degraded_floors(weights))

    for path, expected in ((RERANK_PATH, rerank_expected), (FLOORS_PATH, floors_expected)):
        if check_only:
            if not path.is_file():
                errors.append(f"missing generated config: {path.name}")
                continue
            actual = path.read_text(encoding="utf-8")
            if not actual.startswith(GENERATED_HEADER.strip().split("\n")[0]):
                errors.append(f"{path.name} missing AUTO-GENERATED header")
            if actual != expected:
                errors.append(f"{path.name} out of sync with intent_weights_v2.yaml")
        else:
            path.write_text(expected, encoding="utf-8")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync retrieval configs from intent_weights_v2.yaml")
    parser.add_argument("--check", action="store_true", help="Verify generated files match source")
    args = parser.parse_args()
    errors = sync(check_only=args.check)
    if errors:
        for err in errors:
            print(f"ERROR: {err}", file=sys.stderr)
        return 1
    if args.check:
        print("Retrieval config sync verification passed.")
    else:
        print(f"Synced {RERANK_PATH.name} and {FLOORS_PATH.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
