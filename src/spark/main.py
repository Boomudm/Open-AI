from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Query, Response
from fastapi.openapi.docs import get_redoc_html
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from spark.api.platform.middleware.stack import register_platform_middleware
from spark.api.platform.errors import register_exception_handlers
from spark.api.v1.router import router as api_router
from spark.schemas.openapi_examples import READYZ_DEGRADED, READYZ_OK
from spark.core.cache import Cache, ensure_redis_ready
from spark.core.config import settings
from spark.core.logging import configure_logging, get_logger
from spark.core.readyz_probe import readyz_full, readyz_lite
from spark.ingestion.embedder import assert_dummy_embeddings_allowed
from spark.retrieval.safety.circuit_breaker import bootstrap_rag_circuit_state

configure_logging()

# LangSmith (optional)
os.environ["LANGCHAIN_TRACING_V2"] = str(settings.langchain_tracing_v2).lower()
if settings.langchain_api_key:
    os.environ["LANGCHAIN_API_KEY"] = settings.langchain_api_key
os.environ["LANGCHAIN_PROJECT"] = settings.langchain_project

log = get_logger(__name__)

settings.validate_for_production()
settings.validate_profile_env()
settings.validate_app_profile()
assert_dummy_embeddings_allowed()


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info(
        "spark_started",
        env=settings.app_env,
        llm_profile=settings.llm_profile,
        llm=settings.ollama_llm_model,
        embed=settings.ollama_embed_model,
        auth_required=settings.effective_auth_required,
        app_profile_fail_closed=settings.app_profile.fail_closed_on_missing_auth,
        app_profile_redis_required=settings.app_profile.redis_required,
    )
    await _run_migrations_on_startup()
    await bootstrap_rag_circuit_state()
    from spark.ingestion.config_validator import validate_ingest_contracts_at_startup

    validate_ingest_contracts_at_startup()
    from spark.core.production_lock import validate_production_lock_at_startup

    validate_production_lock_at_startup(spark_profile=settings.spark_profile)
    from spark.retrieval.rerank.cross_encoder import validate_gpu_rerank_at_startup

    validate_gpu_rerank_at_startup()
    from spark.core.deprecated_config import audit_deprecated_config

    audit_deprecated_config()
    from spark.core.startup_checks import run_all_startup_checks

    await run_all_startup_checks()
    await ensure_redis_ready(redis_required=settings.app_profile.redis_required)
    asyncio.create_task(_reconcile_qdrant_collections_background())
    asyncio.create_task(_warm_retrieval_models_background())
    if settings.llm_profile == "demo" and settings.app_env.strip().lower() != "development":
        log.warning(
            "llm_profile_demo_non_dev",
            detail="LLM_PROFILE=demo uses qwen2.5:3b — set gemma/gemma_remote for production (qwen3.6:35b-a3b via gateway)",
        )
    if settings.is_production and not settings.auth_required:
        log.warning("auth_required_forced_in_production")
    if not settings.effective_auth_required:
        log.warning(
            "auth_demo_mode_open",
            detail="AUTH_REQUIRED=false — unauthenticated API requests run as admin; never expose on the internet",
        )
    yield
    log.info("spark_shutdown_start")
    await _graceful_shutdown()
    log.info("spark_shutdown_complete")


async def _graceful_shutdown() -> None:
    """Drain connections and release resources on shutdown."""
    from spark.core.database import engine, stream_engine

    try:
        await engine.dispose()
        await stream_engine.dispose()
        log.info("db_pools_disposed")
    except Exception as exc:
        log.warning("db_dispose_failed", error=str(exc)[:200])

    try:
        cache = Cache.get()
        client = getattr(cache, "_redis", None)
        if client is not None and hasattr(client, "aclose"):
            await client.aclose()
        log.info("redis_closed")
    except Exception as exc:
        log.warning("redis_close_failed", error=str(exc)[:200])

    try:
        from spark.core.qdrant import close_qdrant_clients

        await close_qdrant_clients()
        log.info("qdrant_clients_closed")
    except Exception as exc:
        log.warning("qdrant_close_failed", error=str(exc)[:200])


async def _run_migrations_on_startup() -> None:
    """Apply Alembic migrations at boot so a fresh DB has all tables (prevents 500s).

    Disable with RUN_MIGRATIONS_ON_STARTUP=false (e.g. when a separate job owns
    migrations). Uses alembic/env.py, which reads settings.database_url_sync.
    """
    if os.getenv("RUN_MIGRATIONS_ON_STARTUP", "true").strip().lower() not in (
        "1",
        "true",
        "yes",
    ):
        return
    from pathlib import Path

    from alembic import command
    from alembic.config import Config

    project_root = Path(__file__).resolve().parents[2]
    cfg = Config(str(project_root / "alembic.ini"))
    try:
        await asyncio.to_thread(command.upgrade, cfg, "head")
        log.info("alembic_upgrade_complete")
    except Exception as exc:
        log.error("alembic_upgrade_failed", error=str(exc)[:300])
        raise


async def _reconcile_qdrant_collections_background() -> None:
    """Best-effort Qdrant collection reconcile — does not block request workers."""
    from sqlalchemy import select

    from spark.core.qdrant import ensure_collection, ensure_enterprise_collection
    from spark.core.qdrant_strategy import list_search_collections
    from spark.core.database import AsyncSessionLocal
    from spark.db.models.org import Factory

    try:
        async with AsyncSessionLocal() as session:
            factory_ids = (
                await session.execute(select(Factory.factory_id))
            ).scalars().all()

        def _ensure_all() -> None:
            for factory_id in factory_ids:
                for coll in list_search_collections(factory_id):
                    ensure_collection(coll)
            ensure_enterprise_collection()

        await asyncio.to_thread(_ensure_all)
        log.info("qdrant_collections_reconciled", factories=len(factory_ids))
    except Exception as exc:
        log.warning("qdrant_reconcile_background_failed", error=str(exc)[:200])


async def _warm_retrieval_models_background() -> None:
    """Pay the retrieval models' lazy-load cost at startup, not on a user's query.

    The bge-m3 sparse leg builds a fast tokenizer from sentencepiece on first
    use: measured 11.7s on this Jetson, then ~0ms (it is lru_cached per process).
    Left lazy, that whole cost lands on the first query after every restart or
    deploy — it dominated a cold retrieval (12.6s vector leg vs 28ms warm) and
    could burn the request budget before generation even started. Warming the
    dense embedder likewise takes its ~0.4s cold path off that first query.

    Runs as a background task and swallows failures: this is an optimisation, so
    it must never keep the app from serving. Both encoders stay lazily
    initialised, so a failure here just restores the previous lazy-load
    behaviour on first use.
    """
    import time as _time

    try:
        started = _time.perf_counter()

        def _warm_sparse() -> None:
            from spark.ingestion.index.sparse.encoder import get_sparse_encoder

            get_sparse_encoder().encode_query("warmup")

        await asyncio.to_thread(_warm_sparse)
        sparse_ms = round((_time.perf_counter() - started) * 1000, 1)

        dense_started = _time.perf_counter()
        from spark.ingestion.embedder import Embedder

        await Embedder.get().embed_query("warmup")
        dense_ms = round((_time.perf_counter() - dense_started) * 1000, 1)

        log.info("retrieval_models_warmed", sparse_ms=sparse_ms, dense_ms=dense_ms)
    except Exception as exc:
        log.warning("retrieval_warmup_background_failed", error=str(exc)[:200])


app = FastAPI(
    title="Neo Chat API",
    description="Factory knowledge chat — on-prem AI",
    version="1.0.0",
    docs_url="/docs",
    # FastAPI 0.115 still points ReDoc at redoc@next on jsDelivr, which 404s and
    # leaves /redoc blank. Serve our own page with a pinned working bundle.
    redoc_url=None,
    lifespan=lifespan,
)

register_exception_handlers(app)
register_platform_middleware(app)

app.include_router(api_router)


@app.get("/redoc", include_in_schema=False)
async def redoc_html():
    return get_redoc_html(
        openapi_url=app.openapi_url or "/openapi.json",
        title=f"{app.title} - ReDoc",
        redoc_js_url="https://cdn.jsdelivr.net/npm/redoc@2.1.5/bundles/redoc.standalone.js",
    )


@app.get("/", tags=["Health"])
async def root():
    return {
        "system": "Neo Chat",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs",
    }


@app.get("/healthz", tags=["Health"], responses={200: {"content": {"application/json": {"example": {"status": "ok"}}}}})
async def healthz():
    return {"status": "ok"}


@app.get(
    "/readyz",
    tags=["Health"],
    responses={
        200: {
            "description": "Dependency readiness",
            "content": {
                "application/json": {
                    "examples": {
                        "ready": {"value": READYZ_OK},
                        "degraded": {"value": READYZ_DEGRADED},
                    }
                }
            },
        },
        503: {"description": "Critical dependency down"},
    },
)
async def readyz(lite: bool = Query(False), deep: bool = Query(False)):
    if lite:
        body, status = await readyz_lite()
    else:
        body, status = await readyz_full(bypass_cache=deep)
    if status != 200:
        return JSONResponse(status_code=status, content=body)
    return body


@app.get("/metrics", tags=["Health"])
async def metrics():
    data = generate_latest()
    return Response(content=data, media_type=CONTENT_TYPE_LATEST)
