#!/usr/bin/env python3
"""Fail CI when tracked docs advertise stale config/env surface."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

STALE_PATTERNS: tuple[tuple[str, str], ...] = (
    ("RERANKER_STRATEGY", "Reranker is always cross-encoder via RERANKER_MODEL"),
    ("RAG_HYBRID_RETRIEVAL_ENABLED", "Hybrid retrieval is always on; remove legacy flag"),
    ("nomic-embed-text", "Default embed model is BAAI/bge-m3 (1024-dim) via LLM_PROFILE"),
    ("RAGFLOW_API_URL", "RAGFlow removed — use native ingest only"),
)

SCAN_PATHS = [
    ROOT / "README.md",
    ROOT / ".env.example",
    ROOT / ".env.factory.example",
    ROOT / "docs" / "integrations.md",
    ROOT / "docs" / "architecture.md",
    ROOT / ".github" / "workflows" / "ci.yml",
    ROOT / "web" / "components" / "landing",
]

ALLOWLIST_SUFFIXES = (
    "CHANGELOG.md",
    "validate_config_docs.py",
    "architecture-th-tech-report.md",
    "demo_playbook.md",
    "customer_demo_guide.md",
    "runbook.md",
    "evaluation-baseline.md",
    "TEAM_SYSTEM_OVERVIEW.md",
    "development-roadmap-th.md",
    "development-roadmap-checklist-th.md",
    "v0.6-native-only.md",
)

SRC_RAGFLOW_ALLOWLIST = (
    ROOT / "src" / "spark" / "core" / "deprecated_config.py",
)


def _is_allowlisted(path: Path) -> bool:
    name = path.name
    if name in ALLOWLIST_SUFFIXES:
        return True
    if "remediation_plan" in path.parts:
        return True
    if "archive" in path.parts:
        return True
    if "legacy" in path.parts:
        return True
    return False


def main() -> int:
    violations: list[str] = []
    for base in SCAN_PATHS:
        if base.is_file():
            paths = [base]
        elif base.is_dir():
            paths = sorted(p for p in base.rglob("*") if p.is_file())
        else:
            continue
        for path in paths:
            if not path.is_file() or _is_allowlisted(path):
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            for pattern, hint in STALE_PATTERNS:
                if pattern in text:
                    violations.append(f"{path.relative_to(ROOT)}: contains {pattern!r} — {hint}")

    src_root = ROOT / "src"
    if src_root.is_dir():
        for path in sorted(src_root.rglob("*")):
            if not path.is_file() or path.suffix not in {".py"}:
                continue
            if path in SRC_RAGFLOW_ALLOWLIST:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            if "ragflow" in text.lower():
                violations.append(
                    f"{path.relative_to(ROOT)}: contains ragflow reference — native-only spine"
                )

    if violations:
        print("Stale configuration documentation detected:", file=sys.stderr)
        for item in violations:
            print(f"  - {item}", file=sys.stderr)
        return 1

    print("Config documentation surface OK.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
