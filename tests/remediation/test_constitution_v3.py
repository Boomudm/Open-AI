"""Constitution v3 contract tests (remediation blueprint v3 Phase 0)."""

from __future__ import annotations

from pathlib import Path

from spark.retrieval.kernel import RAGKernelInput

ROOT = Path(__file__).resolve().parents[2]

# Baseline captured at Phase 0 — no new shim modules under services/rag/ (Phase 13 deletes tree).
SERVICES_RAG_SHIM_BASELINE: frozenset[str] = frozenset(
    {
        "src/spark/services/rag/__init__.py",
        "src/spark/services/rag/cache.py",
        "src/spark/services/rag/circuit_breaker.py",
        "src/spark/services/rag/compat.py",
        "src/spark/services/rag/evidence_spans.py",
        "src/spark/services/rag/extractive_pipeline.py",
        "src/spark/services/rag/fallback_policy.py",
        "src/spark/services/rag/follow_up.py",
        "src/spark/services/rag/fusion.py",
        "src/spark/services/rag/fusion_v2.py",
        "src/spark/services/rag/grounded_generate.py",
        "src/spark/services/rag/hybrid.py",
        "src/spark/services/rag/ingest_generation.py",
        "src/spark/services/rag/lexical/__init__.py",
        "src/spark/services/rag/numeric_grounding.py",
        "src/spark/services/rag/query_rewrite.py",
        "src/spark/services/rag/rate_limit.py",
        "src/spark/services/rag/rerank.py",
        "src/spark/services/rag/retrieval.py",
    }
)


def test_production_lock_v2_documents_v3_migration() -> None:
    path = ROOT / "configs" / "production_lock_v2.yaml"
    text = path.read_text(encoding="utf-8")
    assert "production_lock_v3" in text or "remediation_blueprint_v3" in text


def test_no_new_services_rag_shim_modules() -> None:
    rag_dir = ROOT / "src" / "spark" / "services" / "rag"
    if not rag_dir.is_dir():
        return
    current = frozenset(
        str(p.relative_to(ROOT)).replace("\\", "/")
        for p in rag_dir.rglob("*.py")
    )
    new_modules = current - SERVICES_RAG_SHIM_BASELINE
    assert new_modules == frozenset(), f"New services/rag shim modules detected: {sorted(new_modules)}"


def test_rag_kernel_input_has_deadline_started_at_field() -> None:
    fields = {f.name for f in RAGKernelInput.__dataclass_fields__.values()}
    assert "deadline_started_at" in fields


def test_import_spine_v3_module_patterns_defined() -> None:
    from spark.contracts.import_spine import (
        FORBIDDEN_IMPORT_PATTERNS_V3,
        V3_PHASE_ENFORCED_PATTERNS,
    )

    assert len(FORBIDDEN_IMPORT_PATTERNS_V3) >= len(V3_PHASE_ENFORCED_PATTERNS)
