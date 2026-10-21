"""Load query blocklist patterns from YAML with TTL-based hot-reload (Phase 10).

Remediation v4: patterns reload every 60s without restart.
"""

from __future__ import annotations

import time
from pathlib import Path

import yaml

_DEFAULT_PATH = Path(__file__).resolve().parents[4] / "configs" / "security" / "query_blocklist.yaml"
_RELOAD_INTERVAL_SEC = 60

_cached_patterns: tuple[str, ...] = ()
_cached_at: float = 0.0
_cached_path: str | None = None


def load_query_blocklist_patterns(path: str | None = None) -> tuple[str, ...]:
    global _cached_patterns, _cached_at, _cached_path

    resolved_path = path or str(_DEFAULT_PATH)
    now = time.monotonic()

    if _cached_patterns and _cached_path == resolved_path and (now - _cached_at) < _RELOAD_INTERVAL_SEC:
        return _cached_patterns

    cfg_path = Path(resolved_path)
    if not cfg_path.is_file():
        return _cached_patterns or ()

    raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    categories = raw.get("categories") or {}
    patterns: list[str] = []
    if isinstance(categories, dict):
        for items in categories.values():
            if isinstance(items, list):
                patterns.extend(str(item) for item in items if item)

    _cached_patterns = tuple(patterns)
    _cached_at = now
    _cached_path = resolved_path
    return _cached_patterns
