from __future__ import annotations

import time
from pathlib import Path

from spark.core.config import settings
from spark.core.logging import get_logger

log = get_logger(__name__)


def ingest_temp_dir() -> Path:
    target = settings.ingest_temp_dir.expanduser().resolve()
    target.mkdir(parents=True, exist_ok=True)
    return target


def cleanup_stale_ingest_temp(max_age_seconds: int | None = None) -> int:
    """Remove ingest temp files older than TTL. Returns count removed."""
    ttl = max_age_seconds if max_age_seconds is not None else settings.ingest_temp_ttl_seconds
    directory = ingest_temp_dir()
    if not directory.is_dir():
        return 0

    now = time.time()
    removed = 0
    for path in directory.iterdir():
        if not path.is_file():
            continue
        try:
            age_seconds = now - path.stat().st_mtime
        except OSError:
            continue
        if age_seconds <= ttl:
            continue
        try:
            size_bytes = path.stat().st_size
            path.unlink(missing_ok=True)
            removed += 1
            log.warning(
                "ingest_temp_stale_removed",
                path=str(path),
                age_seconds=int(age_seconds),
                size_bytes=size_bytes,
            )
        except OSError as exc:
            log.warning(
                "ingest_temp_stale_remove_failed",
                path=str(path),
                error=str(exc)[:120],
            )

    if removed:
        log.info("ingest_temp_cleanup_done", removed=removed, directory=str(directory))
    return removed
