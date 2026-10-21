"""Factory RAG tuning wired from FactoryConfigService."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from spark.services.factory_config_service import FactoryConfigService
from spark.retrieval.models import RetrievedDoc
from spark.retrieval.tuning import RagTuningContext
from spark.services.rag_service import rag_service


def _doc(score: float) -> RetrievedDoc:
    return RetrievedDoc(
        page_content="bearing cooling fan 80C",
        score=score,
        vector_score=score,
        payload={"text": "bearing cooling fan 80C"},
    )


def test_rag_tuning_from_factory_config_uses_overrides() -> None:
    svc = FactoryConfigService()
    cfg = {
        "rag": {
            "top_k_default": 8,
            "min_max_score": 0.7,
            "min_avg_score": 0.5,
            "chunk_profile": "semantic_form_th",
        }
    }
    tuning = svc.rag_tuning(cfg)
    assert tuning.top_k_default == 8
    assert tuning.min_max_score == 0.7
    assert tuning.min_avg_score == 0.5
    assert tuning.chunk_profile == "semantic_form_th"


def test_rag_tuning_defaults_when_factory_values_null() -> None:
    # Defaults now live on the authoritative [0,1] rerank-relevance scale.
    tuning = RagTuningContext.from_factory_config({"rag": {"min_max_score": None}})
    assert tuning.min_max_score == pytest.approx(0.35)
    assert tuning.min_avg_score == pytest.approx(0.25)


def test_passes_relevance_respects_factory_min_scores() -> None:
    docs = [_doc(0.6), _doc(0.58), _doc(0.57)]
    assert rag_service._passes_relevance(docs) is True
    assert rag_service._passes_relevance(docs, min_max_score=0.65, min_avg_score=0.55) is False


@pytest.mark.asyncio
async def test_factory_config_resolve_merges_rag_overrides() -> None:
    svc = FactoryConfigService()
    db = MagicMock()
    db.get = AsyncMock(return_value=None)
    cfg = await svc.resolve(db, "F-01")
    assert cfg["rag"]["top_k_default"] == 6
    overrides = svc.rag_overrides(cfg)
    assert "top_k_default" in overrides
