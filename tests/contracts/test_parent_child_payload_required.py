"""Parent-child chunking requires parent hydration fields in parser payload."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from spark.contracts.rag_payload_contract import required_parser_fields_for_strategy
from spark.ingestion.index.qdrant_writer import QdrantWriter
from spark.ingestion.parsers.base import ParsedRecord


def test_page_aware_parent_child_requires_parent_fields() -> None:
    required = required_parser_fields_for_strategy("page_aware_parent_child")
    assert "parent_chunk_id" in required
    assert "parent_content" in required
    assert "page" in required


@pytest.mark.asyncio
async def test_qdrant_writer_rejects_missing_parent_child_fields() -> None:
    writer = QdrantWriter(batch_size=8)
    embed_profile = MagicMock()
    embed_profile.dimension = 4
    embed_profile.model_id = "m"
    embed_profile.model = "m"
    embed_profile.version = "1"
    embed_profile.provider = "p"
    writer.embedder = MagicMock()
    writer.embedder.embed_profile = MagicMock(return_value=embed_profile)
    pool = MagicMock()
    pool.encode_dense_batch = AsyncMock(return_value=[[0.1, 0.2, 0.3, 0.4]])
    pool.encode_sparse_batch = AsyncMock(return_value=[])
    writer._compute_pool = pool
    writer.sparse_encoder = MagicMock(encoder_id="none")

    record = ParsedRecord(
        route="qdrant",
        payload={"page_content": "child only", "chunk_index": 0},
        text_for_embedding="child only",
    )
    session = AsyncMock()
    session.add_all = MagicMock()
    session.flush = AsyncMock()
    session.rollback = AsyncMock()

    with patch("spark.ingestion.index.qdrant_writer.get_async_qdrant_client") as client_factory:
        client = MagicMock()
        client.upsert = AsyncMock()
        client_factory.return_value = client
        with patch("spark.ingestion.index.qdrant_writer.ensure_collection"):
            with patch("spark.ingestion.index.qdrant_writer.embed_lineage_for_text", return_value={
                "embed_model_id": "m",
                "embed_model": "m",
                "embed_model_version": "1",
                "embed_provider": "p",
                "embed_dimension": 4,
                "config_hash": "cfg",
                "content_hash": "hash",
                "chunk_schema_version": 1,
            }):
                with patch("spark.ingestion.index.qdrant_writer.enrich_chunk_lexical", return_value=("", [])):
                    with patch("spark.services.document_access_service.restricted_position_ids_for_docs", new_callable=AsyncMock, return_value={}):
                        with pytest.raises(ValueError, match="missing parser payload fields"):
                            await writer.write(
                                [record],
                                uuid.uuid4(),
                                {"chunking": {"strategy": "page_aware_parent_child"}, "qdrant": {}},
                                {"factory_id": "F-01", "document_type": "machine_manual", "config_hash": "cfg"},
                                session,
                            )
