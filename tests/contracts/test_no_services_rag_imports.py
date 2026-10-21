"""Contract: Phase 13 — no imports from deleted spark.services.rag package."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_services_rag_package_removed() -> None:
    assert not (ROOT / "src" / "spark" / "services" / "rag").exists()


def test_no_services_rag_imports_in_src() -> None:
    _rag = "spark.services." + "rag"
    _rag_svc = _rag + "_service"
    violations: list[str] = []
    for path in sorted((ROOT / "src").rglob("*.py")):
        rel = str(path.relative_to(ROOT))
        text = path.read_text(encoding="utf-8")
        if _rag in text and _rag_svc not in text:
            violations.append(rel)
        elif f"from {_rag} " in text or f"import {_rag} " in text:
            violations.append(rel)
    assert violations == [], f"Forbidden services.rag imports: {violations}"
