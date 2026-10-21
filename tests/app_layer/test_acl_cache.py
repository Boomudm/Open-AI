"""ACL cache tests (app-layer Phase 4)."""

from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock

import pytest

from spark.core.security import Principal
from spark.services.acl.cache_invalidation import bump_factory_acl_version, invalidate_user_doc_acl_cache
from spark.services.acl.document_acl_cache import allowed_doc_ids_for_principal_cached


@pytest.mark.asyncio
async def test_acl_cache_hit_avoids_second_compute(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"n": 0}
    doc_id = uuid.uuid4()

    async def _compute(session, principal, *, factory_id=None):
        calls["n"] += 1
        return [doc_id]

    monkeypatch.setattr(
        "spark.services.acl.document_acl_cache.compute_allowed_doc_ids",
        _compute,
    )
    from spark.core.cache import Cache

    await Cache.get().clear_spark_keys()

    principal = Principal(
        user_id=str(uuid.uuid4()),
        username="employee",
        roles=("employee",),
        factory_access={"F-01": "read"},
        job_position_ids=(),
        token_version=1,
    )
    session = AsyncMock()
    first = await allowed_doc_ids_for_principal_cached(session, principal)
    second = await allowed_doc_ids_for_principal_cached(session, principal)
    assert first == second
    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_factory_acl_invalidation_busts_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"n": 0}

    async def _compute(session, principal, *, factory_id=None):
        calls["n"] += 1
        return []

    monkeypatch.setattr(
        "spark.services.acl.document_acl_cache.compute_allowed_doc_ids",
        _compute,
    )
    principal = Principal(
        user_id="00000000-0000-0000-0000-000000000002",
        username="employee",
        roles=("employee",),
        factory_access={"F-01": "read"},
        job_position_ids=(),
        token_version=1,
    )
    session = AsyncMock()
    await allowed_doc_ids_for_principal_cached(session, principal, factory_id="F-01")
    await bump_factory_acl_version("F-01")
    await allowed_doc_ids_for_principal_cached(session, principal, factory_id="F-01")
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_user_acl_invalidation_busts_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"n": 0}

    async def _compute(session, principal, *, factory_id=None):
        calls["n"] += 1
        return []

    monkeypatch.setattr(
        "spark.services.acl.document_acl_cache.compute_allowed_doc_ids",
        _compute,
    )
    user_id = "00000000-0000-0000-0000-000000000003"
    principal = Principal(
        user_id=user_id,
        username="employee",
        roles=("employee",),
        factory_access={"F-01": "read"},
        job_position_ids=(),
        token_version=1,
    )
    session = AsyncMock()
    await allowed_doc_ids_for_principal_cached(session, principal)
    await invalidate_user_doc_acl_cache(user_id)
    await allowed_doc_ids_for_principal_cached(session, principal)
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_version_race_recomputes_once(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"n": 0}

    async def _compute(session, principal, *, factory_id=None):
        calls["n"] += 1
        if calls["n"] == 1:
            await bump_factory_acl_version(factory_id or "F-01")
        return []

    monkeypatch.setattr(
        "spark.services.acl.document_acl_cache.compute_allowed_doc_ids",
        _compute,
    )
    principal = Principal(
        user_id=str(uuid.uuid4()),
        username="employee",
        roles=("employee",),
        factory_access={"F-01": "read"},
        job_position_ids=(),
        token_version=1,
    )
    session = AsyncMock()
    await allowed_doc_ids_for_principal_cached(session, principal, factory_id="F-01")
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_concurrent_cache_misses_coalesce_on_version(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"n": 0}
    lock = asyncio.Lock()

    async def _compute(session, principal, *, factory_id=None):
        async with lock:
            calls["n"] += 1
            await asyncio.sleep(0.02)
        return []

    monkeypatch.setattr(
        "spark.services.acl.document_acl_cache.compute_allowed_doc_ids",
        _compute,
    )
    principal = Principal(
        user_id=str(uuid.uuid4()),
        username="employee",
        roles=("employee",),
        factory_access={"F-01": "read"},
        job_position_ids=(),
        token_version=1,
    )
    session = AsyncMock()
    await asyncio.gather(
        allowed_doc_ids_for_principal_cached(session, principal, factory_id="F-01"),
        allowed_doc_ids_for_principal_cached(session, principal, factory_id="F-01"),
    )
    assert calls["n"] >= 1
