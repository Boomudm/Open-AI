from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from spark.ingestion.parsers.base import ParsedRecord
from spark.ingestion.index.qdrant_writer import QdrantRouter


@pytest.mark.asyncio
async def test_qdrant_router_mirrors_chunk_text_and_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    doc_id = uuid.uuid4()
    inserted = []
    upserted = []

    class FakeEmbedder:
        async def embed_documents(self, texts):
            return [[0.1, 0.2, 0.3] for _ in texts]

        def embed_profile(self):
            from spark.ingestion.embed_profile import EmbedProfile

            return EmbedProfile(
                model_id="test-embed",
                provider="ollama",
                dimension=3,
                llm_profile="test",
            )

    class FakeClient:
        async def upsert(self, *, collection_name, points, wait):
            upserted.append((collection_name, points, wait))

    class FakeSession:
        def add_all(self, rows):
            inserted.extend(rows)

        async def flush(self) -> None:
            return None

        async def rollback(self) -> None:
            return None

        async def execute(self, *_args, **_kwargs):
            return None

    monkeypatch.setattr("spark.ingestion.index.qdrant_writer.get_async_qdrant_client", lambda: FakeClient())
    monkeypatch.setattr("spark.ingestion.index.qdrant_writer.ensure_collection", lambda *_args, **_kwargs: None)
    # FakeEmbedder emits 3-d vectors; align the strict dim assertion to the fixture.
    monkeypatch.setattr("spark.ingestion.index.qdrant_writer.embedding_dimension", lambda: 3)

    router = QdrantRouter(batch_size=10)
    router.embedder = FakeEmbedder()  # type: ignore[assignment]

    async def fake_dense_batch(texts: list[str]) -> list[list[float]]:
        return [[0.1, 0.2, 0.3] for _ in texts]

    monkeypatch.setattr(router._compute_pool, "encode_dense_batch", fake_dense_batch)
    with patch(
        "spark.services.document_access_service.restricted_position_ids_for_docs",
        new_callable=AsyncMock,
        return_value={},
    ):
        count = await router.write(
            [
                ParsedRecord(
                    route="qdrant",
                    payload={
                        "page_content": "MC-001 cooling fan must be checked above 80°C.",
                        "page": 13,
                        "chunk_index": 7,
                    },
                    text_for_embedding="MC-001 cooling fan must be checked above 80°C.",
                )
            ],
            doc_id=doc_id,
            config={"qdrant": {}},
            document_context={
                "factory_id": "F-01",
                "machine_id": "MC-001",
                "document_category": "knowledge",
                "document_type": "machine_manual",
                "language": "th",
                "source_file": "manual.pdf",
                "title": "Manual",
            },
            session=FakeSession(),  # type: ignore[arg-type]
        )

    assert count == 1
    assert upserted
    assert len(inserted) == 1
    chunk = inserted[0]
    assert chunk.content == "MC-001 cooling fan must be checked above 80°C."
    assert chunk.payload["page_content"] == "MC-001 cooling fan must be checked above 80°C."
    assert chunk.payload["machine_id"] == "MC-001"
    assert chunk.payload["source_file"] == "manual.pdf"
    assert chunk.ingest_generation == 1
    assert chunk.payload["ingest_generation"] == 1
