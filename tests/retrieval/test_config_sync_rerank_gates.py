"""Phase 9 — generated rerank gates stay synced with intent weights."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def test_rerank_gates_auto_generated_header() -> None:
    text = (ROOT / "configs" / "retrieval" / "rerank_gates.yaml").read_text(encoding="utf-8")
    assert text.startswith("# AUTO-GENERATED from intent_weights_v2.yaml")


def test_min_max_matches_intent_weights_min_rerank_score() -> None:
    weights = yaml.safe_load(
        (ROOT / "configs" / "retrieval" / "intent_weights_v2.yaml").read_text(encoding="utf-8")
    )
    gates = yaml.safe_load(
        (ROOT / "configs" / "retrieval" / "rerank_gates.yaml").read_text(encoding="utf-8")
    )
    for name, gate_spec in (gates.get("intents") or {}).items():
        src = (weights.get("intents") or {}).get(name) or weights.get("defaults") or {}
        expected = float(src.get("min_rerank_score", 0.35))
        assert float(gate_spec["min_max"]) == expected


def test_sync_check_script_passes() -> None:
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "sync_retrieval_configs.py"), "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
