"""Per-factory document ID index for ACL compute (app-layer v2 Phase 4)."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from spark.core.cache import Cache
from spark.core.logging import get_logger

log = get_logger(__name__)

_INDEX_TTL_SEC = 7 * 86400


def _index_key(factory_id: str) -> str:
    return f"spark:factory:{factory_id}:doc_index"


async def add_factory_doc(factory_id: str, doc_id: uuid.UUID) -> None:
    if not factory_id:
        return
    key = _index_key(factory_id)
    cache = Cache.get()
    raw = await cache.get_json(key)
    ids: set[str] = set()
    if isinstance(raw, dict) and isinstance(raw.get("doc_ids"), list):
        ids = {str(item) for item in raw["doc_ids"]}
    ids.add(str(doc_id))
    await cache.set_json(key, {"doc_ids": sorted(ids)}, ttl=_INDEX_TTL_SEC)


async def remove_factory_doc(factory_id: str, doc_id: uuid.UUID) -> None:
    if not factory_id:
        return
    key = _index_key(factory_id)
    cache = Cache.get()
    raw = await cache.get_json(key)
    if not isinstance(raw, dict) or not isinstance(raw.get("doc_ids"), list):
        return
    ids = {str(item) for item in raw["doc_ids"] if str(item) != str(doc_id)}
    if ids:
        await cache.set_json(key, {"doc_ids": sorted(ids)}, ttl=_INDEX_TTL_SEC)
    else:
        await cache.delete(key)


async def list_factory_doc_ids(factory_id: str) -> set[uuid.UUID] | None:
    """Return indexed doc IDs, or None when the index is absent (caller falls back to SQL)."""
    if not factory_id:
        return None
    raw = await Cache.get().get_json(_index_key(factory_id))
    if not isinstance(raw, dict) or not isinstance(raw.get("doc_ids"), list):
        return None
    out: set[uuid.UUID] = set()
    for item in raw["doc_ids"]:
        try:
            out.add(uuid.UUID(str(item)))
        except ValueError:
            continue
    return out


async def rebuild_factory_doc_index(session: AsyncSession, factory_id: str) -> int:
    """Rebuild index from Postgres (cold-cache / miss path)."""
    from spark.db.models.docs import Document

    rows = (
        await session.execute(
            select(Document.doc_id).where(Document.factory_id == factory_id)
        )
    ).scalars().all()
    ids = sorted(str(doc_id) for doc_id in rows)
    key = _index_key(factory_id)
    await Cache.get().set_json(key, {"doc_ids": ids}, ttl=_INDEX_TTL_SEC)
    log.debug("factory_doc_index_rebuilt", factory_id=factory_id, count=len(ids))
    return len(ids)
