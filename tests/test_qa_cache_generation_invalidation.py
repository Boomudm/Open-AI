"""Phase 12 — QA cache invalidates when cited chunk generation changes."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from spark.core.config import settings
from spark.services.qa_cache_service import (
    QACacheService,
    build_cache_fingerprint,
)


@pytest.mark.asyncio
async def test_cache_fingerprint_includes_generation_hash(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "qa_cache_enabled", True)
    svc = QACacheService()
    db = MagicMock()
    chunk_id = str(uuid.uuid4())
    sources = [{"chunk_id": chunk_id, "doc_id": str(uuid.uuid4())}]

    async def fake_build_fingerprint(*_args, **kwargs):
        return "fp-current"

    async def fake_generation_hash(_db, _factory_id):
        return "gen-v1"

    monkeypatch.setattr(
        "spark.services.qa_cache_service.build_cache_fingerprint",
        fake_build_fingerprint,
    )
    monkeypatch.setattr(
        "spark.services.qa_cache_service.active_generation_hash_for_factory",
        fake_generation_hash,
    )

    row = MagicMock()
    row.filter_fingerprint = "fp-stale"
    row.expires_at = None
    row.sources = sources
    row.source_doc_ids = []
    row.answer_text = "cached"
    row.cache_id = uuid.uuid4()
    row.hit_count = 0

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [row]
    db.execute = AsyncMock(return_value=mock_result)
    db.flush = AsyncMock()
    svc._docs_still_valid = AsyncMock(return_value=True)
    svc._chunks_still_valid = AsyncMock(return_value=True)

    hit = await svc.lookup(
        db,
        factory_id="F-01",
        question="bearing torque",
        principal=None,
    )
    assert hit is None


@pytest.mark.asyncio
async def test_chunks_still_valid_misses_when_generation_snapshot_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    svc = QACacheService()
    db = MagicMock()
    sources = [
        {
            "chunk_id": str(uuid.uuid4()),
            "_cache_meta": {
                "chunk_snapshot_hash": "hash-gen-1",
                "embed_model_version": "profile:v1@ollama",
            },
        }
    ]

    monkeypatch.setattr(
        "spark.services.qa_cache_service.chunk_snapshot_hash",
        AsyncMock(return_value="hash-gen-2"),
    )
    monkeypatch.setattr(
        "spark.services.qa_cache_service.EmbedProfile.from_runtime",
        lambda *_args, **_kwargs: MagicMock(version="profile:v1@ollama"),
    )

    assert await svc._chunks_still_valid(db, sources, "fp-current") is False


@pytest.mark.asyncio
async def test_build_cache_fingerprint_dimensions(monkeypatch: pytest.MonkeyPatch) -> None:
    db = MagicMock()
    monkeypatch.setattr(
        "spark.services.qa_cache_service.resolve_embed_profile_for_factory",
        AsyncMock(
            return_value=MagicMock(model_id="embed-model", version="profile:v1@ollama")
        ),
    )
    monkeypatch.setattr(
        "spark.services.qa_cache_service.active_generation_hash_for_factory",
        AsyncMock(return_value="gen-hash"),
    )
    monkeypatch.setattr(
        "spark.services.qa_cache_service.load_ingest_policy_version",
        lambda: "policy-v3",
    )
    monkeypatch.setattr(
        "spark.services.qa_cache_service.load_intent_weight_version",
        lambda: "2",
    )

    fp = await build_cache_fingerprint(
        db,
        factory_id="F-01",
        machine_id="MC-001",
        doc_type="sop",
    )
    assert len(fp) == 64
    fp2 = await build_cache_fingerprint(
        db,
        factory_id="F-01",
        machine_id="MC-002",
        doc_type="sop",
    )
    assert fp != fp2
