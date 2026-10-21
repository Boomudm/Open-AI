"""RagFusionConfig fields must be consumed by fusion code paths."""

from __future__ import annotations

from dataclasses import fields
from pathlib import Path

from spark.retrieval.tuning import RagFusionConfig


def test_rag_fusion_config_fields_are_used() -> None:
    root = Path(__file__).resolve().parents[1]
    fusion_py = (root / "src" / "spark" / "retrieval" / "fusion.py").read_text(encoding="utf-8")
    retrieval_py = (root / "src" / "spark" / "retrieval" / "engine.py").read_text(encoding="utf-8")
    tuning_py = (root / "src" / "spark" / "retrieval" / "tuning.py").read_text(encoding="utf-8")
    combined = fusion_py + retrieval_py + tuning_py
    for field in fields(RagFusionConfig):
        assert field.name in combined, f"RagFusionConfig.{field.name} appears unused in fusion stack"
    assert "sparse_weight" not in combined
