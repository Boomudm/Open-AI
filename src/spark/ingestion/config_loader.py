from __future__ import annotations

from functools import lru_cache
from typing import Any

import yaml

from spark.core.config import settings


@lru_cache(maxsize=64)
def load_config(document_type: str) -> dict[str, Any]:
    cfg_path = settings.config_dir / f"{document_type}.yaml"
    if not cfg_path.exists():
        raise FileNotFoundError(f"Ingestion config not found: {cfg_path}")
    with cfg_path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Invalid config (not a mapping): {cfg_path}")
    data.setdefault("document_type", document_type)
    return data


def list_document_types() -> list[str]:
    if not settings.config_dir.exists():
        return []
    return sorted(p.stem for p in settings.config_dir.glob("*.yaml"))


def clear_cache() -> None:
    load_config.cache_clear()
    from spark.ingestion.config_resolver import clear_profile_caches

    clear_profile_caches()
