"""Load compliance taxonomy for export and retention gates."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_TAXONOMY_PATH = _PROJECT_ROOT / "configs" / "compliance" / "data_classification.yaml"


@lru_cache(maxsize=1)
def load_data_classification() -> dict[str, Any]:
    if not _TAXONOMY_PATH.is_file():
        raise FileNotFoundError(f"Missing taxonomy: {_TAXONOMY_PATH}")
    raw = yaml.safe_load(_TAXONOMY_PATH.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError("data_classification.yaml must be a mapping")
    return raw


def document_type_entry(document_type: str | None) -> dict[str, Any]:
    raw = load_data_classification()
    types = raw.get("document_types") or {}
    aliases = raw.get("aliases") or {}
    key = str(document_type or "generic")
    resolved = str(aliases.get(key) or key)
    entry = types.get(resolved) or types.get("generic") or {}
    return dict(entry) if isinstance(entry, dict) else {}


def export_settings() -> dict[str, Any]:
    raw = load_data_classification()
    export = raw.get("export") or {}
    return dict(export) if isinstance(export, dict) else {}


def classification_levels() -> frozenset[str]:
    raw = load_data_classification()
    types = raw.get("document_types") or {}
    levels: set[str] = set()
    for entry in types.values():
        if isinstance(entry, dict) and entry.get("classification_level"):
            levels.add(str(entry["classification_level"]))
    return frozenset(levels)


def document_types_for_level(level: str) -> frozenset[str]:
    raw = load_data_classification()
    types = raw.get("document_types") or {}
    aliases = raw.get("aliases") or {}
    matched: set[str] = set()
    for name, entry in types.items():
        if isinstance(entry, dict) and str(entry.get("classification_level") or "") == level:
            matched.add(str(name))
    for alias, target in aliases.items():
        if target in matched:
            matched.add(str(alias))
    return frozenset(matched)
