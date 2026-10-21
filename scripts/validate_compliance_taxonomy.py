#!/usr/bin/env python3
"""Validate ingestion document types against compliance taxonomy (Phase 14)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
INGEST_DIR = ROOT / "configs" / "ingestion"
TAXONOMY_PATH = ROOT / "configs" / "compliance" / "data_classification.yaml"

REQUIRED_FIELDS = ("classification_level", "retention_days", "export_allowed", "pii_handling")


def _load_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path} must be a mapping")
    return data


def load_taxonomy(path: Path = TAXONOMY_PATH) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    raw = _load_yaml(path)
    document_types = raw.get("document_types") or {}
    if not isinstance(document_types, dict) or not document_types:
        raise ValueError("data_classification.yaml missing document_types mapping")
    aliases = raw.get("aliases") or {}
    if not isinstance(aliases, dict):
        raise ValueError("data_classification.yaml aliases must be a mapping")
    parsed: dict[str, dict[str, Any]] = {}
    for name, entry in document_types.items():
        if not isinstance(entry, dict):
            raise ValueError(f"document_types.{name} must be a mapping")
        parsed[str(name)] = entry
    return parsed, {str(k): str(v) for k, v in aliases.items()}


def ingest_document_types() -> dict[str, Path]:
    found: dict[str, Path] = {}
    for path in sorted(INGEST_DIR.glob("*.yaml")):
        raw = _load_yaml(path)
        doc_type = str(raw.get("document_type") or path.stem).strip()
        if not doc_type:
            raise ValueError(f"{path} missing document_type")
        found[doc_type] = path
    return found


def validate_taxonomy(*, taxonomy_path: Path = TAXONOMY_PATH, strict: bool = True) -> list[str]:
    errors: list[str] = []
    document_types, aliases = load_taxonomy(taxonomy_path)

    for name, entry in document_types.items():
        if name == "generic":
            continue
        for field in REQUIRED_FIELDS:
            if field not in entry:
                errors.append(f"document_types.{name} missing required field {field!r}")

    ingest_types = ingest_document_types()
    if not ingest_types:
        errors.append(f"no ingestion configs under {INGEST_DIR}")

    for doc_type, path in ingest_types.items():
        resolved = aliases.get(doc_type, doc_type)
        if resolved not in document_types:
            errors.append(f"ingestion type {doc_type!r} ({path.name}) has no taxonomy entry")
            continue
        entry = document_types[resolved]
        for field in REQUIRED_FIELDS:
            if field not in entry:
                errors.append(f"taxonomy entry {resolved!r} missing {field!r} (via {doc_type})")

    orphan_types = set(document_types) - {"generic"}
    used_taxonomy_keys = {aliases.get(doc_type, doc_type) for doc_type in ingest_types}
    for name in sorted(orphan_types):
        if name not in used_taxonomy_keys and strict:
            errors.append(f"orphan taxonomy entry {name!r} — no configs/ingestion/*.yaml")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate compliance taxonomy coverage")
    parser.add_argument(
        "--taxonomy",
        type=Path,
        default=TAXONOMY_PATH,
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail on orphan taxonomy entries without ingestion config",
    )
    args = parser.parse_args()

    try:
        errors = validate_taxonomy(taxonomy_path=args.taxonomy, strict=args.strict)
    except (FileNotFoundError, ValueError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1

    if errors:
        for err in errors:
            print(f"FAIL: {err}", file=sys.stderr)
        return 1

    ingest_count = len(ingest_document_types())
    print(f"OK compliance taxonomy: {ingest_count} ingestion types covered")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
