"""Phase 5 — sparse encode must not run synchronously on the asyncio event loop."""

from __future__ import annotations

import threading
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from qdrant_client.models import SparseVector

from spark.ingestion.index.compute_pool import IngestComputePool
from spark.ingestion.index.qdrant_writer import QdrantWriter
from spark.ingestion.parsers.base import ParsedRecord


def _make_records(count: int) -> list[ParsedRecord]:
    return [
        ParsedRecord(
            route="qdrant",
            payload={"page_content": f"chunk {index}", "chunk_index": index},
            text_for_embedding=f"chunk {index}",
        )
        for index in range(count)
    ]


@pytest.fixture(autouse=True)
def _reset_pool() -> None:
    IngestComputePool.reset_for_tests()
    yield
    IngestComputePool.reset_for_tests()


@pytest.mark.asyncio
async def test_qdrant_writer_never_calls_sync_encode_document(monkeypatch: pytest.MonkeyPatch) -> None:
    """1000-chunk fixture: per-record encode_document must not run on the hot path."""
    batch_worker_threads: list[int] = []

    def _fake_dense(texts: list[str]) -> list[list[float]]:
        return [[0.1, 0.2, 0.3, 0.4] for _ in texts]

    def _fake_sparse(texts: list[str]) -> list[SparseVector]:
        batch_worker_threads.append(threading.get_ident())
        return [SparseVector(indices=[1], values=[1.0]) for _ in texts]

    monkeypatch.setattr("spark.ingestion.index.compute_pool.encode_dense_sync", _fake_dense)
    monkeypatch.setattr("spark.ingestion.index.compute_pool.encode_sparse_sync_batch", _fake_sparse)

    writer = QdrantWriter(batch_size=32)
    embed_profile = MagicMock()
    embed_profile.dimension = 4
    writer.embedder = MagicMock()
    writer.embedder.embed_profile = MagicMock(return_value=embed_profile)
    sparse_encoder = MagicMock(encoder_id="bge_m3")
    writer.sparse_encoder = sparse_encoder

    session = AsyncMock()
    session.add_all = MagicMock()
    session.flush = AsyncMock()
    session.rollback = AsyncMock()

    main_thread = threading.get_ident()
    records = _make_records(1000)

    with patch("spark.ingestion.index.qdrant_writer.get_async_qdrant_client") as client_factory:
        client = MagicMock()
        client.upsert = AsyncMock()
        client_factory.return_value = client
        with patch("spark.ingestion.index.qdrant_writer.ensure_collection"):
            with patch("spark.ingestion.index.qdrant_writer.sparse_vectors_enabled", return_value=True):
                with patch(
                    "spark.ingestion.index.qdrant_writer.embed_lineage_for_text",
                    return_value={
                        "embed_model_id": "m",
                        "embed_model": "m",
                        "embed_model_version": "1",
                        "embed_provider": "p",
                        "embed_dimension": 4,
                        "config_hash": "cfg",
                        "content_hash": "hash",
                        "chunk_schema_version": 1,
                    },
                ):
                    with patch(
                        "spark.ingestion.index.qdrant_writer.enrich_chunk_lexical",
                        return_value=("", []),
                    ):
                        with patch("spark.services.document_access_service.restricted_position_ids_for_docs", new_callable=AsyncMock, return_value={}):
                            written = await writer.write(
                                records,
                                uuid.uuid4(),
                                {"chunking": {"strategy": "recursive"}, "qdrant": {}},
                                {
                                    "factory_id": "F-01",
                                    "document_type": "machine_manual",
                                    "config_hash": "cfg",
                                },
                                session,
                            )

    assert written == 1000
    assert batch_worker_threads
    assert all(tid != main_thread for tid in batch_worker_threads)
    sparse_encoder.encode_document.assert_not_called()
