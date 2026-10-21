"""Phase 14 — compliance taxonomy coverage for ingestion document types."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def test_all_ingestion_types_have_taxonomy_entry() -> None:
    taxonomy = yaml.safe_load(
        (ROOT / "configs" / "compliance" / "data_classification.yaml").read_text(encoding="utf-8")
    )
    document_types = taxonomy.get("document_types") or {}
    aliases = taxonomy.get("aliases") or {}

    ingest_dir = ROOT / "configs" / "ingestion"
    ingest_types: list[str] = []
    for path in sorted(ingest_dir.glob("*.yaml")):
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        ingest_types.append(str(raw.get("document_type") or path.stem))

    # Guard against the glob silently matching nothing (renamed dir, packaging
    # change) — the real invariant is the per-type taxonomy check below, not a
    # magic count that goes stale whenever document types are added or removed.
    assert ingest_types, "no ingestion document-type configs found"
    for doc_type in ingest_types:
        resolved = aliases.get(doc_type, doc_type)
        assert resolved in document_types, f"missing taxonomy for {doc_type}"
        entry = document_types[resolved]
        for field in ("classification_level", "retention_days", "export_allowed", "pii_handling"):
            assert field in entry, f"{resolved} missing {field}"


def test_safety_manual_is_alias_not_orphan() -> None:
    taxonomy = yaml.safe_load(
        (ROOT / "configs" / "compliance" / "data_classification.yaml").read_text(encoding="utf-8")
    )
    aliases = taxonomy.get("aliases") or {}
    document_types = taxonomy.get("document_types") or {}
    assert "safety_manual" not in document_types
    assert aliases.get("safety_manual") == "safety_certificate"


def test_validate_compliance_taxonomy_script_passes() -> None:
    script = ROOT / "scripts" / "validate_compliance_taxonomy.py"
    result = subprocess.run(
        [sys.executable, str(script), "--strict"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout
