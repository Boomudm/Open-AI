"""Contract: remediation v2 import spine — forbidden patterns (Phase 13)."""

from __future__ import annotations

from pathlib import Path

from spark.contracts.import_spine import (
    FORBIDDEN_IMPORT_PATTERNS,
    scan_python_source,
)

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "spark"

IMPORT_SPINE_V2_ALLOWLIST: frozenset[str] = frozenset(
    {
        "tests/test_chunking_strategy.py",
    }
)


def _collect_violations() -> list[str]:
    hits: list[str] = []
    for path in sorted(SRC.rglob("*.py")):
        rel = str(path.relative_to(ROOT))
        if rel in IMPORT_SPINE_V2_ALLOWLIST:
            continue
        text = path.read_text(encoding="utf-8")
        for violation in scan_python_source(rel, text):
            hits.append(f"{violation.path}:{violation.line_number}: {violation.line}")
    for path in sorted((ROOT / "tests").rglob("*.py")):
        rel = str(path.relative_to(ROOT))
        if rel.endswith("test_import_spine_v2.py") or rel.endswith("test_import_spine_v3.py"):
            continue
        if rel in IMPORT_SPINE_V2_ALLOWLIST:
            continue
        text = path.read_text(encoding="utf-8")
        for violation in scan_python_source(rel, text):
            hits.append(f"{violation.path}:{violation.line_number}: {violation.line}")
    return hits


def test_import_spine_v2_patterns_defined() -> None:
    assert len(FORBIDDEN_IMPORT_PATTERNS) >= 4


def test_import_spine_v2_manifest_module_exists() -> None:
    path = ROOT / "src" / "spark" / "contracts" / "import_spine.py"
    assert path.is_file()


def test_import_spine_v2_no_forbidden_imports() -> None:
    violations = _collect_violations()
    assert violations == [], "Forbidden import spine v2 violations:\n" + "\n".join(violations)
