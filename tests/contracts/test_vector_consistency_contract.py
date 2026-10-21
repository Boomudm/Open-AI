"""Contract: Phase 11 vector consistency and ops."""

from __future__ import annotations


def test_phase11_exports() -> None:
    from spark.core.qdrant_strategy import apply_collection_suffix, collection_suffix_version
    from spark.ingestion.embed_lineage import embed_lineage_for_text
    from spark.services.vector_reconcile_service import run_vector_reconcile, vector_reconcile_service
    from spark.workers.tasks_policy_rescan import policy_rescan_task
    from spark.workers.tasks_reconcile import reconcile_all_factories_task, reconcile_vectors_task

    assert callable(embed_lineage_for_text)
    assert callable(run_vector_reconcile)
    assert callable(reconcile_vectors_task)
    assert callable(reconcile_all_factories_task)
    assert callable(policy_rescan_task)
    assert vector_reconcile_service is not None
    assert callable(apply_collection_suffix)
    assert isinstance(collection_suffix_version(), str)


def test_document_chunk_lineage_columns() -> None:
    from spark.db.models.docs import DocumentChunk

    for col in ("content_hash", "embed_model", "embed_model_version", "chunk_schema_version"):
        assert col in DocumentChunk.__table__.columns


def test_qdrant_payload_contract_includes_lineage() -> None:
    from spark.contracts.rag_payload_contract import QDRANT_PAYLOAD_FIELDS

    assert {"embed_model", "embed_model_version", "content_hash"}.issubset(QDRANT_PAYLOAD_FIELDS)
