"""Contract: remediation v3 import spine — forbidden patterns and phase-gated bans."""

from __future__ import annotations

from pathlib import Path


from spark.contracts.import_spine import (
    FORBIDDEN_IMPORT_PATTERNS_V3,
    V3_PHASE_ENFORCED_PATTERNS,
    scan_python_source_v3,
)

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "spark"

IMPORT_SPINE_V3_ALLOWLIST: frozenset[str] = frozenset(
    {
        "tests/test_chunking_strategy.py",
    }
)


def _collect_v3_violations(*, enforced_only: bool) -> list[str]:
    hits: list[str] = []
    patterns = V3_PHASE_ENFORCED_PATTERNS if enforced_only else FORBIDDEN_IMPORT_PATTERNS_V3
    for path in sorted(SRC.rglob("*.py")):
        rel = str(path.relative_to(ROOT))
        if rel in IMPORT_SPINE_V3_ALLOWLIST:
            continue
        text = path.read_text(encoding="utf-8")
        for violation in scan_python_source_v3(rel, text, patterns=patterns):
            hits.append(f"{violation.path}:{violation.line_number}: {violation.line}")
    for path in sorted((ROOT / "tests").rglob("*.py")):
        rel = str(path.relative_to(ROOT))
        if rel.endswith("test_import_spine_v3.py"):
            continue
        if rel in IMPORT_SPINE_V3_ALLOWLIST:
            continue
        text = path.read_text(encoding="utf-8")
        for violation in scan_python_source_v3(rel, text, patterns=patterns):
            hits.append(f"{violation.path}:{violation.line_number}: {violation.line}")
    return hits


def test_import_spine_v3_patterns_defined() -> None:
    assert len(FORBIDDEN_IMPORT_PATTERNS_V3) >= 1


def test_import_spine_v3_phase_enforced_subset() -> None:
    assert all(p in FORBIDDEN_IMPORT_PATTERNS_V3 for p in V3_PHASE_ENFORCED_PATTERNS)


def test_import_spine_v3_no_forbidden_imports() -> None:
    violations = _collect_v3_violations(enforced_only=True)
    assert violations == [], "Forbidden import spine v3 violations:\n" + "\n".join(violations)


def test_import_spine_v3_no_calibrate_scores_imports() -> None:
    gate_path = ROOT / "src" / "spark" / "retrieval" / "rerank" / "gate.py"
    pipeline_path = ROOT / "src" / "spark" / "retrieval" / "rerank" / "pipeline.py"
    service_path = ROOT / "src" / "spark" / "retrieval" / "service.py"
    for path in (gate_path, pipeline_path, service_path):
        source = path.read_text(encoding="utf-8")
        assert "calibrate_fusion_scores" not in source
        assert "calibrate_scores" not in source
    assert not (ROOT / "src" / "spark" / "retrieval" / "rerank" / "calibrate_scores.py").exists()


def test_import_spine_v3_no_global_circuit_outcomes_key() -> None:
    """Phase 8 — global spark:rag:circuit:outcomes must not be used for recording."""
    import re

    bare_outcomes = re.compile(r"^\s*OUTCOMES_KEY\s*=", re.MULTILINE)
    for path in (ROOT / "src").rglob("*.py"):
        rel = path.relative_to(ROOT).as_posix()
        text = path.read_text(encoding="utf-8")
        if rel.endswith("retrieval/circuit/dependency_breaker.py"):
            assert "LEGACY_OUTCOMES_KEY" in text
            assert not bare_outcomes.search(text)
            continue
        if "circuit_breaker" in rel or "retrieval/circuit/" in rel:
            assert not bare_outcomes.search(text)
            assert '"spark:rag:circuit:outcomes"' not in text or "LEGACY" in text


def test_scan_python_source_v3_detects_sample_violation() -> None:
    module = "hybrid"
    sample = f"from spark.services.rag.{module} import foo\n"
    hits = scan_python_source_v3("sample.py", sample)
    assert hits
