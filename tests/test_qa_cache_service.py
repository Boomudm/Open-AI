from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from spark.core.config import settings
from spark.core.security import Principal
from spark.db.models.qa_cache import VerifiedQACache
from spark.services.qa_cache_service import (
    QACacheService,
    filter_fingerprint,
    question_hash,
)


def _expected_fingerprint(
    *,
    factory_id: str | None,
    machine_id: str | None = None,
    doc_type: str | None = None,
) -> str:
    return filter_fingerprint(
        factory_id=factory_id,
        machine_id=machine_id,
        doc_type=doc_type,
        embed_model_id="test-embed",
        embed_model_version="test:v1@ollama",
        active_generation_hash="gen-v1",
        policy_version="policy-v1",
        intent_weight_version="1",
    )


@pytest.fixture
def mock_cache_fingerprint(monkeypatch):
    async def _build(_db, **kwargs):
        return _expected_fingerprint(
            factory_id=kwargs.get("factory_id"),
            machine_id=kwargs.get("machine_id"),
            doc_type=kwargs.get("doc_type"),
        )

    monkeypatch.setattr(
        "spark.services.qa_cache_service.build_cache_fingerprint",
        _build,
    )
    monkeypatch.setattr(
        "spark.services.qa_cache_service.resolve_embed_profile_for_factory",
        AsyncMock(return_value=MagicMock(model_id="test-embed", version="test:v1@ollama")),
    )
    monkeypatch.setattr(
        "spark.services.qa_cache_service.active_generation_hash_for_factory",
        AsyncMock(return_value="gen-v1"),
    )
    monkeypatch.setattr(
        "spark.services.qa_cache_service.chunk_snapshot_hash",
        AsyncMock(return_value=None),
    )


def test_question_hash_normalizes_whitespace_and_case() -> None:
    assert question_hash("  What  IS   Bearing?  ") == question_hash("what is bearing?")


def test_filter_fingerprint_stable() -> None:
    a = filter_fingerprint(
        factory_id="F1",
        machine_id="MC-001",
        embed_model_id="test-embed",
        embed_model_version="test:v1@ollama",
        active_generation_hash="gen-v1",
        policy_version="policy-v1",
        intent_weight_version="1",
    )
    b = filter_fingerprint(
        factory_id="F1",
        machine_id="MC-001",
        embed_model_id="test-embed",
        embed_model_version="test:v1@ollama",
        active_generation_hash="gen-v1",
        policy_version="policy-v1",
        intent_weight_version="1",
    )
    c = filter_fingerprint(
        factory_id="F1",
        machine_id="MC-002",
        embed_model_id="test-embed",
        embed_model_version="test:v1@ollama",
        active_generation_hash="gen-v1",
        policy_version="policy-v1",
        intent_weight_version="1",
    )
    assert a == b
    assert a != c


@pytest.mark.asyncio
async def test_lookup_uses_indexed_hash_not_full_scan(
    monkeypatch,
    mock_cache_fingerprint,
) -> None:
    monkeypatch.setattr(settings, "qa_cache_enabled", True)
    svc = QACacheService()
    db = MagicMock()
    row = VerifiedQACache(
        cache_id=uuid.uuid4(),
        factory_id="F1",
        intent="factual",
        question_text="bearing model",
        question_hash=question_hash("bearing model"),
        filter_fingerprint=_expected_fingerprint(factory_id="F1"),
        answer_text="SKF 6205",
        sources=[],
        source_doc_ids=[],
        verification_method="admin",
        hit_count=0,
    )
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [row]
    db.execute = AsyncMock(return_value=mock_result)
    db.flush = AsyncMock()
    db.get = AsyncMock(return_value=MagicMock(is_active=True, retrieval_enabled=True))

    hit = await svc.lookup(
        db,
        factory_id="F1",
        question="  Bearing Model  ",
        principal=Principal(
            user_id="00000000-0000-0000-0000-000000000001",
            username="admin",
            roles=("admin",),
            factory_access={},
        ),
    )
    assert hit is not None
    assert hit["cache_hit"] is True
    assert hit["answer"] == "SKF 6205"
    stmt = db.execute.await_args.args[0]
    compiled = str(stmt)
    assert "question_hash" in compiled


@pytest.mark.asyncio
async def test_lookup_miss_when_filter_fingerprint_differs(
    monkeypatch,
    mock_cache_fingerprint,
) -> None:
    monkeypatch.setattr(settings, "qa_cache_enabled", True)
    svc = QACacheService()
    db = MagicMock()
    row = VerifiedQACache(
        cache_id=uuid.uuid4(),
        factory_id="F1",
        machine_id="MC-001",
        intent="factual",
        question_text="bearing model",
        question_hash=question_hash("bearing model"),
        filter_fingerprint=_expected_fingerprint(factory_id="F1", machine_id="MC-001"),
        answer_text="SKF 6205",
        sources=[],
        source_doc_ids=[],
        verification_method="admin",
        hit_count=0,
    )
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [row]
    db.execute = AsyncMock(return_value=mock_result)

    hit = await svc.lookup(
        db,
        factory_id="F1",
        question="bearing model",
        principal=Principal(
            user_id="00000000-0000-0000-0000-000000000001",
            username="admin",
            roles=("admin",),
            factory_access={},
        ),
        machine_id="MC-002",
    )
    assert hit is None


@pytest.mark.asyncio
async def test_lookup_miss_after_expiry(monkeypatch, mock_cache_fingerprint) -> None:
    monkeypatch.setattr(settings, "qa_cache_enabled", True)
    svc = QACacheService()
    db = MagicMock()
    row = VerifiedQACache(
        cache_id=uuid.uuid4(),
        factory_id="F1",
        intent="factual",
        question_text="bearing model",
        question_hash=question_hash("bearing model"),
        filter_fingerprint=_expected_fingerprint(factory_id="F1"),
        answer_text="SKF 6205",
        sources=[],
        source_doc_ids=[],
        verification_method="admin",
        hit_count=0,
        expires_at=datetime.now(tz=UTC) - timedelta(days=1),
    )
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [row]
    db.execute = AsyncMock(return_value=mock_result)

    hit = await svc.lookup(
        db,
        factory_id="F1",
        question="bearing model",
        principal=None,
    )
    assert hit is None


@pytest.mark.asyncio
async def test_verify_message_sets_verified_at(
    monkeypatch,
    mock_cache_fingerprint,
) -> None:
    monkeypatch.setattr(settings, "qa_cache_enabled", True)
    from spark.db.models.chat import ChatMessage

    svc = QACacheService()
    db = MagicMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.get = AsyncMock(return_value=MagicMock(is_active=True, retrieval_enabled=True))

    msg = ChatMessage(
        message_id=uuid.uuid4(),
        session_id=uuid.uuid4(),
        role="assistant",
        content="SKF 6205",
        sources=[],
    )
    principal = Principal(
        user_id="00000000-0000-0000-0000-000000000001",
        username="admin",
        roles=("admin",),
        factory_access={},
    )
    await svc.verify_message(
        db,
        message=msg,
        factory_id="F1",
        question_text="bearing?",
        principal=principal,
    )
    assert msg.verified_at is not None
