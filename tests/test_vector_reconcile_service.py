"""Tests for vector reconcile service (Phase 11)."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from spark.db.models.docs import Document
from spark.services.vector_reconcile_service import VectorReconcileService


@pytest.mark.asyncio
async def test_reconcile_auto_fix_deletes_superseded_only() -> None:
    doc_id = uuid.uuid4()
    doc = Document(
        doc_id=doc_id,
        factory_id="F-01",
        document_category="knowledge",
        document_type="machine_manual",
        source_file="manual.pdf",
        chunks_count=3,
        active_ingest_generation=2,
        ingest_status="completed",
    )

    class FakeSession:
        async def scalar(self, _stmt):
            return 3

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
    router.count_by_doc = AsyncMock(return_value=5)

    service = VectorReconcileService()
    with patch(
        "spark.services.vector_reconcile_service.QdrantWriter",
        return_value=router,
    ), patch(
        "spark.services.vector_reconcile_service.save_last_reconcile_result",
    ), patch(
        "spark.services.vector_reconcile_service.vector_drift_detected_total"
    ) as metric:
        result = await service.reconcile(
            FakeSession(),  # type: ignore[arg-type]
            auto_fix=True,
        )

    router.delete_by_doc_except_generation.assert_called_once()
    call_kwargs = router.delete_by_doc_except_generation.call_args.kwargs
    assert call_kwargs["keep_generation"] == 2
    assert result.fixed_count == 1
    metric.labels.assert_called()
