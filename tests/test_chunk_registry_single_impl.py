"""Phase 6 — one implementation per chunk strategy name."""

from __future__ import annotations

import ast
from pathlib import Path

from spark.ingestion.chunk.strategies import get_chunking_strategy


def test_chunk_strategies_have_single_registry_entry() -> None:
    from spark.ingestion.chunk.types import CANONICAL_CHUNK_STRATEGIES

    for name in sorted(CANONICAL_CHUNK_STRATEGIES):
        strategy = get_chunking_strategy(name)
        assert strategy is not None


def test_legacy_strategy_module_deleted() -> None:
    root = Path(__file__).resolve().parents[1]
    assert not (root / "src/spark/ingestion/chunking/strategy.py").exists()


def test_no_duplicate_parent_child_implementations() -> None:
    root = Path(__file__).resolve().parents[1]
    ingestion_root = root / "src/spark/ingestion"
    hits: list[str] = []
    for path in ingestion_root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == "ParentChildChunker":
                hits.append(str(path.relative_to(ingestion_root)))
    assert hits == ["chunk/parent_child.py"]
