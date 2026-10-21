"""Centralized system constants loader — single source for all tuning parameters."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

_CONSTANTS_PATH = Path(__file__).resolve().parents[3] / "configs" / "system_constants.yaml"


@lru_cache(maxsize=1)
def load_system_constants() -> dict[str, Any]:
    if not _CONSTANTS_PATH.is_file():
        return {}
    with _CONSTANTS_PATH.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data if isinstance(data, dict) else {}


def get_constant(section: str, key: str, default: Any = None) -> Any:
    constants = load_system_constants()
    section_data = constants.get(section) or {}
    if isinstance(section_data, dict):
        return section_data.get(key, default)
    return default


def clear_constants_cache() -> None:
    load_system_constants.cache_clear()
