"""Per-factory configuration resolution for RAG, ingest, notifications."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from spark.core.config import settings
from spark.db.models.factory_settings import FactorySettings

_DEFAULTS: dict[str, Any] = {
    "rag": {
        "min_max_score": None,
        "min_avg_score": None,
        "top_k_default": 6,
        "chunk_profile": "long_form_th",
        "fusion_method": "rrf",
        "dense_weight": 0.7,
        "lexical_weight": 0.3,
        "rrf_k": None,
    },
    "ingest": {
        "backend": "native",
        "chunking_strategy": "recursive",
    },
    "notifications": {
        "enabled": False,
        "channels": [],
        "insights_hotness": True,
        "ingest_failed": True,
        "ocr_low_confidence": True,
    },
    "llm_profile": None,
    "timezone": "Asia/Bangkok",
    "features": {},
}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


# Raw settings change rarely but are resolved on every chat query (fusion
# config + lexical engine + circuit profile) — a short in-process TTL cache
# removes 2-3 Postgres round-trips per question. Writes invalidate the entry
# immediately in this process; other API processes converge within the TTL.
_RAW_CACHE_TTL_SEC = 30.0


class FactoryConfigService:
    def __init__(self) -> None:
        self._raw_cache: dict[str, tuple[float, dict[str, Any]]] = {}

    def invalidate(self, factory_id: str | None = None) -> None:
        if factory_id is None:
            self._raw_cache.clear()
        else:
            self._raw_cache.pop(factory_id, None)

    async def get_raw(self, db: AsyncSession, factory_id: str) -> dict[str, Any]:
        import time as _time

        cached = self._raw_cache.get(factory_id)
        now = _time.monotonic()
        if cached is not None and now - cached[0] < _RAW_CACHE_TTL_SEC:
            return deepcopy(cached[1])
        row = await db.get(FactorySettings, factory_id)
        raw = dict(row.settings or {}) if row else {}
        self._raw_cache[factory_id] = (now, deepcopy(raw))
        return raw

    async def resolve(self, db: AsyncSession, factory_id: str | None) -> dict[str, Any]:
        resolved = deepcopy(_DEFAULTS)
        if settings.llm_profile:
            resolved["llm_profile"] = settings.llm_profile
        if not factory_id:
            return resolved
        raw = await self.get_raw(db, factory_id)
        return _deep_merge(resolved, raw)

    async def resolve_many(
        self, db: AsyncSession, factory_ids: list[str]
    ) -> dict[str, dict[str, Any]]:
        if not factory_ids:
            return {}
        rows = (
            await db.execute(
                select(FactorySettings).where(FactorySettings.factory_id.in_(factory_ids))
            )
        ).scalars().all()
        stored = {row.factory_id: dict(row.settings or {}) for row in rows}
        out: dict[str, dict[str, Any]] = {}
        for factory_id in factory_ids:
            resolved = deepcopy(_DEFAULTS)
            if settings.llm_profile:
                resolved["llm_profile"] = settings.llm_profile
            out[factory_id] = _deep_merge(resolved, stored.get(factory_id, {}))
        return out

    async def upsert(
        self, db: AsyncSession, factory_id: str, patch: dict[str, Any]
    ) -> dict[str, Any]:
        row = await db.get(FactorySettings, factory_id)
        if row is None:
            row = FactorySettings(factory_id=factory_id, settings=patch)
            db.add(row)
        else:
            row.settings = _deep_merge(dict(row.settings or {}), patch)
        await db.flush()
        self.invalidate(factory_id)
        return dict(row.settings or {})

    def rag_overrides(self, config: dict[str, Any]) -> dict[str, Any]:
        return config.get("rag") or {}

    def rag_tuning(self, config: dict[str, Any]):
        from spark.retrieval.tuning import RagTuningContext

        return RagTuningContext.from_factory_config(config)

    def rag_fusion(self, config: dict[str, Any]):
        from spark.retrieval.tuning import RagFusionConfig

        return RagFusionConfig.from_factory_config(config)

    def ingest_backend(self, config: dict[str, Any]) -> str:
        from spark.ingestion.constants import INGEST_BACKEND

        _ = config
        return INGEST_BACKEND

    def timezone(self, config: dict[str, Any]) -> str:
        return str(config.get("timezone") or "Asia/Bangkok")

    def production_profile(self, config: dict[str, Any]):
        from spark.core.production_profile import ProductionProfile

        return ProductionProfile.for_factory(config)

    def remediation_flags(self, config: dict[str, Any]):
        """Back-compat alias — use production_profile()."""
        return self.production_profile(config)


factory_config_service = FactoryConfigService()
