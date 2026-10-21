"""Phase 5 — vector store schema v2, lineage, reconcile, swap verify."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from spark.core.qdrant import DENSE_VECTOR_NAME, SPARSE_VECTOR_NAME, sparse_vectors_enabled
from spark.ingestion.embed_profile import EmbedProfile
from spark.ingestion.index.swap_verify import IndexDriftError, verify_generation_counts
from spark.retrieval.models import RAGFilter, _build_qdrant_filter
from spark.services.vector_reconcile_service import VectorReconcileService


def test_qdrant_schema_v2_vector_names() -> None:
    assert DENSE_VECTOR_NAME == "dense"
    assert SPARSE_VECTOR_NAME == "sparse"


def test_sparse_enabled_by_default_outside_test_profile() -> None:
    from spark.core.config import settings

    original = settings.spark_profile
    try:
        settings.spark_profile = "production"
        settings.sparse_vectors_disabled = False
        assert sparse_vectors_enabled() is True
    finally:
        settings.spark_profile = original


def test_retrieval_filter_embed_model_version() -> None:
    qfilter = _build_qdrant_filter(RAGFilter(factory_id="F-01"))
    assert qfilter is not None
    keys = [getattr(c, "key", None) for c in qfilter.must]
    assert "embed_model_version" in keys


@pytest.mark.asyncio
async def test_swap_verify_fails_when_qdrant_count_low() -> None:
    writer = AsyncMock()
    writer.count_by_doc = AsyncMock(return_value=90)
    with pytest.raises(IndexDriftError):
        await verify_generation_counts(
            doc_id=uuid.uuid4(),
            generation=2,
            pg_count=100,
            qdrant_writer=writer,
            collection="spark_docs__f-01",
        )


@pytest.mark.asyncio
async def test_reconcile_reupsert_when_qdrant_missing_points() -> None:
    doc_id = uuid.uuid4()
    from spark.db.models.docs import Document

    doc = Document(
        doc_id=doc_id,
        factory_id="F-01",
        document_category="knowledge",
        document_type="machine_manual",
        source_file="manual.pdf",
        chunks_count=5,
        active_ingest_generation=1,
        ingest_status="completed",
    )

    class FakeSession:
        async def scalar(self, _stmt):
            return 5

        async def execute(self, _stmt):
            class Result:
                def scalars(self):
                    class Scalars:
                        def all(self):
                            return [doc]

                    return Scalars()

            return Result()

        async def commit(self):
            return None

    router = AsyncMock()
    router.count_by_doc = AsyncMock(return_value=2)
    router.reupsert_from_pg_mirror = AsyncMock(return_value=5)

    service = VectorReconcileService()
    with patch(
        "spark.services.vector_reconcile_service.QdrantWriter",
        return_value=router,
    ), patch(
        "spark.services.vector_reconcile_service.save_last_reconcile_result",
    ), patch(
        "spark.services.vector_reconcile_service.vector_drift_detected_total"
    ), patch(
        "spark.services.vector_reconcile_service.ingest_vector_drift_detected_total"
    ):
        result = await service.reconcile(FakeSession(), auto_fix=True)  # type: ignore[arg-type]

    router.reupsert_from_pg_mirror.assert_called_once()
    assert result.reupserted_count == 1
    assert "@" in EmbedProfile.from_runtime().version
