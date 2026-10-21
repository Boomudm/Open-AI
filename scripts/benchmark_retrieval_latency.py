"""Sweep retrieval latency knobs and emit hardware profile recommendations."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
PROFILES_PATH = ROOT / "configs" / "retrieval_hardware_profiles.yaml"


def _load_profiles() -> dict:
    if not PROFILES_PATH.is_file():
        return {"profiles": {}}
    with PROFILES_PATH.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {"profiles": {}}


def _recommend(
    *,
    multiplier: int,
    rerank_max: int,
    p95_ms: float,
    recall: float,
) -> dict:
    return {
        "rag_retrieve_multiplier": multiplier,
        "rag_rerank_max_candidates": rerank_max,
        "estimated_p95_ms": round(p95_ms, 2),
        "estimated_recall": round(recall, 4),
    }


def run_sweep(profile: str) -> dict:
    """Deterministic sweep placeholder — wire to eval harness for live recall numbers."""
    profiles = _load_profiles().get("profiles", {})
    base = profiles.get(profile, {})
    multiplier = int(base.get("rag_retrieve_multiplier", 3))
    rerank_max = int(base.get("rag_rerank_max_candidates", 64))
    rows = []
    for mult in (2, 3, 4):
        for cap in (32, 64, 96):
            latency = 40 + (mult * 12) + (cap * 1.1)
            recall = min(0.99, 0.72 + (mult * 0.03) + (cap / 1000))
            rows.append(_recommend(multiplier=mult, rerank_max=cap, p95_ms=latency, recall=recall))
    best = min(rows, key=lambda row: (row["estimated_p95_ms"], -row["estimated_recall"]))
    return {
        "profile": profile,
        "baseline": base,
        "recommendation": best,
        "sweep": rows,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Benchmark retrieval latency knobs")
    parser.add_argument(
        "--profile",
        default="cpu_default",
        help="Hardware profile key from configs/retrieval_hardware_profiles.yaml",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON")
    args = parser.parse_args(argv)
    result = run_sweep(args.profile)
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        rec = result["recommendation"]
        print(
            f"profile={result['profile']} "
            f"recommended multiplier={rec['rag_retrieve_multiplier']} "
            f"rerank_max={rec['rag_rerank_max_candidates']} "
            f"p95~{rec['estimated_p95_ms']}ms recall~{rec['estimated_recall']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
