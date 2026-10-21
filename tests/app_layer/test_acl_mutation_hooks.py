"""ACL mutation hook tests (app-layer v2 Phase 4)."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from spark.core.cache import Cache
from spark.db.models.docs import Document
from spark.services.acl.cache_invalidation import read_factory_acl_version
from spark.services.acl.mutation_hooks import on_document_positions_changed
from spark.services.ingest_scope import set_document_job_positions


@pytest.fixture(autouse=True)
async def _clear_cache() -> None:
    await Cache.get().clear_spark_keys()
    yield
    await Cache.get().clear_spark_keys()


@pytest.mark.asyncio
async def test_on_document_positions_changed_bumps_factory_version() -> None:
    doc_id = uuid.uuid4()
    await on_document_positions_changed(
        AsyncMock(),
        factory_id="F-ACL-01",
        doc_id=doc_id,
        position_ids=[],
    )
    assert await read_factory_acl_version("F-ACL-01") == 1


@pytest.mark.asyncio
async def test_set_document_job_positions_bumps_factory_version(monkeypatch: pytest.MonkeyPatch) -> None:
    doc_id = uuid.uuid4()
    doc = Document(doc_id=doc_id, factory_id="F-ACL-02", document_type="manual")

    session = AsyncMock()
    session.get = AsyncMock(return_value=doc)
    session.execute = AsyncMock(
        return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[]))))
    )
    session.delete = AsyncMock()
    session.add = MagicMock()

    await set_document_job_positions(session, doc_id, [])
    assert await read_factory_acl_version("F-ACL-02") == 1


@pytest.mark.asyncio
async def test_position_change_invalidates_cached_allowed_docs(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"n": 0}
    doc_id = uuid.uuid4()

    async def _compute(session, principal, *, factory_id=None):
        calls["n"] += 1
        return [doc_id] if calls["n"] == 1 else []

    monkeypatch.setattr(
        "spark.services.acl.document_acl_cache.compute_allowed_doc_ids",
        _compute,
    )

    principal = __import__("spark.core.security", fromlist=["Principal"]).Principal(
        user_id=str(uuid.uuid4()),
        username="employee",
        roles=("employee",),
        factory_access={"F-ACL-03": "read"},
        job_position_ids=(),
        token_version=1,
    )
    session = AsyncMock()

    from spark.services.acl.document_acl_cache import allowed_doc_ids_for_principal_cached

    first = await allowed_doc_ids_for_principal_cached(session, principal, factory_id="F-ACL-03")
    assert first == [doc_id]

    await on_document_positions_changed(
        session,
        factory_id="F-ACL-03",
        doc_id=doc_id,
        position_ids=[],
    )

    second = await allowed_doc_ids_for_principal_cached(session, principal, factory_id="F-ACL-03")
    assert second == []
    assert calls["n"] == 2
