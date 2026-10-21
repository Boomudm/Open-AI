"""Tests for Phase 6 lexical engine (postgres_thai_v3)."""

from __future__ import annotations

import pytest

from spark.retrieval.lexical import get_lexical_retriever
from spark.retrieval.lexical.postgres_thai_v3 import PostgresThaiV3LexicalEngine
from spark.services.rag_service import RAGFilter, RAGService


def test_get_lexical_retriever_thai_v3() -> None:
    assert isinstance(get_lexical_retriever("postgres_thai_v3"), PostgresThaiV3LexicalEngine)


def test_get_lexical_retriever_rejects_legacy_v2() -> None:
    with pytest.raises(ValueError, match="postgres_thai_v3"):
        get_lexical_retriever("postgres_v2")


@pytest.mark.asyncio
async def test_resolve_lexical_engine_uses_test_profile_default(monkeypatch: pytest.MonkeyPatch) -> None:
    from spark.core.config import settings

    monkeypatch.setattr(settings, "spark_profile", "test")

    engine = await RAGService()._resolve_lexical_engine(RAGFilter())
    assert engine == "postgres_thai_v3"


@pytest.mark.asyncio
async def test_resolve_lexical_engine_production_default(monkeypatch: pytest.MonkeyPatch) -> None:
    from spark.core.config import settings

    monkeypatch.setattr(settings, "spark_profile", "production")

    engine = await RAGService()._resolve_lexical_engine(RAGFilter())
    assert engine == "postgres_thai_v3"
