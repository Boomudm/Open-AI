from __future__ import annotations

import os

from celery import Celery
from celery.signals import task_postrun, worker_ready

# Each Celery task calls asyncio.run() (its own throwaway event loop). A pooled
# SQLAlchemy connection checked in at the end of one task stays bound to that
# now-closed loop, so the next task's checkout raises 'RuntimeError: Event loop
# is closed' — and there's no way to clean it up after the fact either, since
# closing an asyncpg connection also requires a live loop. spark.core.database
# reads this flag (must be set before it's imported, hence first thing here) to
# use NullPool instead: every checkout opens a fresh connection and closes it
# within the same task's own loop, so nothing ever persists across tasks.
os.environ.setdefault("SPARK_CELERY_WORKER", "1")

# Ensure Homebrew binaries (pdfinfo, tesseract, etc.) are on PATH for worker subprocesses.
# Homebrew installs to /opt/homebrew/bin on Apple Silicon and /usr/local/bin on Intel.
for _brew_bin in ("/opt/homebrew/bin", "/usr/local/bin"):
    if os.path.isdir(_brew_bin) and _brew_bin not in os.environ.get("PATH", ""):
        os.environ["PATH"] = f"{_brew_bin}:{os.environ['PATH']}"

from spark.core.config import settings  # noqa: E402 — must follow the PATH/env setup above
from spark.core.logging import configure_logging  # noqa: E402
from spark.storage.temp import cleanup_stale_ingest_temp  # noqa: E402

configure_logging()

celery_app = Celery(
    "spark",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=[
        "spark.workers.tasks",
        "spark.workers.tasks_reconcile",
        "spark.workers.tasks_policy_rescan",
        "spark.workers.tasks_trust_release",
        "spark.workers.tasks_ocr",
        "spark.workers.tasks_purge",
    ],
)
celery_app.conf.update(
    task_track_started=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    worker_cancel_long_running_tasks_on_connection_loss=True,
    result_expires=86400,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_default_queue="celery",
    task_routes={
        "spark.workers.tasks_ocr.*": {"queue": "ocr_heavy"},
    },
    beat_schedule={
        "nightly-vector-reconcile": {
            "task": "spark.workers.tasks_reconcile.reconcile_vectors_task",
            "schedule": 86400.0,
            "kwargs": {"auto_fix": True},
        },
        "vector-reconcile-15m": {
            "task": "spark.workers.tasks_reconcile.reconcile_all_factories_task",
            "schedule": 900.0,
            "kwargs": {"auto_fix": True},
        },
        "ingest-temp-cleanup": {
            "task": "spark.workers.tasks.cleanup_ingest_temp_task",
            "schedule": 21600.0,
        },
        "ingest-purge-outbox": {
            "task": "spark.workers.tasks_purge.dispatch_pending_purges",
            "schedule": 300.0,
        },
        "rescue-stuck-pending": {
            "task": "spark.workers.tasks.rescue_stuck_pending_task",
            "schedule": 300.0,
        },
        "weekly-policy-rescan": {
            "task": "spark.workers.tasks_policy_rescan.policy_rescan_task",
            "schedule": 604800.0,
        },
    },
)


@task_postrun.connect
def _reset_qdrant_client_after_task(**_: object) -> None:
    """Drop the cached async Qdrant client after every task.

    Same root cause as the DB engine (see spark.core.database's SPARK_CELERY_WORKER
    handling): each task's asyncio.run() is its own throwaway event loop, and
    AsyncQdrantClient caches an httpx connection pool bound to whichever loop was
    active when it was created. Unlike the DB engine, there's no NullPool
    equivalent for this client, so instead we just drop the reference — the next
    call to get_async_qdrant_client() builds a fresh client on the new loop.
    """
    try:
        from spark.core.qdrant import reset_async_qdrant_client

        reset_async_qdrant_client()
    except Exception:  # pragma: no cover — best-effort teardown
        pass


@worker_ready.connect
def _cleanup_ingest_temp_on_worker_start(**_: object) -> None:
    cleanup_stale_ingest_temp()


def check_celery_worker_health(*, timeout: float = 2.0) -> dict[str, object]:
    """Ping Redis broker queue and confirm at least one Celery worker responds."""
    import redis

    try:
        client = redis.from_url(settings.redis_url, socket_connect_timeout=timeout)
        client.ping()
        client.llen("celery")
    except Exception as exc:
        return {"ok": False, "status": "unavailable", "error": str(exc)[:120]}

    try:
        ping = celery_app.control.inspect(timeout=timeout).ping() or {}
        workers = sorted(ping.keys())
        if workers:
            return {"ok": True, "workers": len(workers), "worker_names": workers}
        return {"ok": False, "status": "unavailable"}
    except Exception as exc:
        return {"ok": False, "status": "unavailable", "error": str(exc)[:120]}
