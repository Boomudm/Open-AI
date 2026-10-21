"""Phase 12 — cache hit re-validation rejects RBAC drift."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from spark.core.security import Principal
from spark.services.qa_cache_validator import revalidate_cache_hit


@pytest.mark.asyncio
async def test_revalidate_cache_hit_rejects_disallowed_doc() -> None:
    doc_id = uuid.uuid4()
    cache_id = uuid.uuid4()
    db = MagicMock()
    db.execute = AsyncMock()

    svc = MagicMock()
    svc._docs_still_valid = AsyncMock(return_value=True)
    svc._chunks_still_valid = AsyncMock(return_value=True)

    valid = await revalidate_cache_hit(
        db,
        cache_id=str(cache_id),
        factory_id="F-01",
        sources=[{"doc_id": str(doc_id), "chunk_id": str(uuid.uuid4())}],
        source_doc_ids=[doc_id],
        principal=Principal(
            user_id=str(uuid.uuid4()),
            username="operator",
            roles=("operator",),
            factory_access={"F-01": "read"},
        ),
        allowed_doc_ids=["00000000-0000-0000-0000-000000000099"],
        expected_fingerprint="fp-current",
        stored_fingerprint="fp-current",
        svc=svc,
    )
    assert valid is False
    db.execute.assert_awaited()


@pytest.mark.asyncio
async def test_revalidate_cache_hit_accepts_matching_fingerprint() -> None:
    doc_id = uuid.uuid4()
    chunk_id = uuid.uuid4()
    cache_id = uuid.uuid4()
    db = MagicMock()

    svc = MagicMock()
    svc._docs_still_valid = AsyncMock(return_value=True)
    svc._chunks_still_valid = AsyncMock(return_value=True)

    async def fake_active_generation(_db, _sources):
        return True

    import spark.services.qa_cache_validator as validator_module

    original = validator_module._chunks_in_active_generation
    validator_module._chunks_in_active_generation = fake_active_generation
    try:
        valid = await revalidate_cache_hit(
            db,
            cache_id=str(cache_id),
            factory_id="F-01",
            sources=[{"doc_id": str(doc_id), "chunk_id": str(chunk_id)}],
            source_doc_ids=[doc_id],
            principal=None,
            allowed_doc_ids=None,
            expected_fingerprint="fp-current",
            stored_fingerprint="fp-current",
            svc=svc,
        )
    finally:
        validator_module._chunks_in_active_generation = original

    assert valid is True
