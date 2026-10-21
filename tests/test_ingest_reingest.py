"""Tests for re-ingest Qdrant cleanup (issue #40).

Integration path requires Postgres + Qdrant (docker compose). Ollama is mocked.
Skips when infrastructure is unavailable.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import func, select

from spark.core.database import AsyncSessionLocal
from spark.core.llm_profile import embedding_dimension
from spark.core.qdrant import ensure_collection
from spark.db.models.docs import Document, DocumentChunk
from spark.db.models.org import Factory, Machine
from spark.ingestion.parsers.base import ParsedRecord
from spark.ingestion.pipeline import (
    _document_registry_updates,
    _prepare_reingest_if_needed,
    run_pipeline,
)
from spark.ingestion.index.qdrant_writer import QdrantRouter

TEST_MACHINE = "TEST-REINGEST"
TEST_FACTORY = "F-01"
V1_CHUNKS = 3
V2_CHUNKS = 2


class FakeEmbedder:
    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[0.1] * embedding_dimension() for _ in texts]

    async def embed_query(self, text: str) -> list[float]:
        return [0.1] * embedding_dimension()

    def embed_profile(self):
        from spark.ingestion.embed_profile import EmbedProfile

        return EmbedProfile(
            model_id="test-embed",
            provider="ollama",
            dimension=embedding_dimension(),
            llm_profile="test",
        )


class FakeManualParser:
    def __init__(self, chunk_count: int) -> None:
        self.chunk_count = chunk_count

    async def parse(self, file_path: Path, config: dict[str, Any]) -> AsyncIterator[ParsedRecord]:
        parent_id = f"{file_path.stem}-parent-0"
        for i in range(self.chunk_count):
            text = f"{file_path.stem}-chunk-{i}"
            yield ParsedRecord(
                route="qdrant",
                payload={
                    "page_content": text,
                    "chunk_index": i,
                    "page": 1,
                    "chunk_level": "child",
                    "parent_chunk_id": parent_id,
                    "parent_content": f"{file_path.stem} parent context",
                },
                text_for_embedding=text,
            )


async def _services_up() -> bool:
    try:
        from spark.core.qdrant import get_async_qdrant_client

        client = get_async_qdrant_client()
        await client.get_collections()
        async with AsyncSessionLocal() as session:
            await session.execute(select(1))
        return True
    except Exception:
        return False


async def _ensure_test_machine() -> None:
    async with AsyncSessionLocal() as session:
        if await session.get(Factory, TEST_FACTORY) is None:
            session.add(
                Factory(
                    factory_id=TEST_FACTORY,
                    factory_name="Bangkok Plant",
                    location="Bangkok",
                )
            )
        if await session.get(Machine, TEST_MACHINE) is None:
            session.add(
                Machine(
                    machine_id=TEST_MACHINE,
                    factory_id=TEST_FACTORY,
                    machine_name="Reingest Test Machine",
                    machine_type="motor",
                )
            )
        await session.commit()


async def _register_doc(doc_id: uuid.UUID, *, revision: str, title: str) -> None:
    async with AsyncSessionLocal() as session:
        session.add(
            Document(
                doc_id=doc_id,
                factory_id=TEST_FACTORY,
                machine_id=TEST_MACHINE,
                document_category="knowledge",
                document_type="machine_manual",
                title=title,
                revision=revision,
                source_file=f"manual-{revision}.pdf",
                ingest_status="pending",
            )
        )
        await session.commit()


async def _cleanup_doc(doc_id: uuid.UUID) -> None:
    router = QdrantRouter()
    async with AsyncSessionLocal() as session:
        await router.clear_for_reingest(doc_id, session)
        doc = await session.get(Document, doc_id)
        if doc:
            await session.delete(doc)
        await session.commit()


def test_document_registry_updates_revision() -> None:
    updates = _document_registry_updates(
        {"revision": "v2", "source_file": "manual-v2.pdf", "title": "Manual v2"},
        chunks_count=5,
        rows_skipped=0,
        rows_skipped_ocr=0,
    )
    assert updates["revision"] == "v2"
    assert updates["source_file"] == "manual-v2.pdf"
    assert updates["title"] == "Manual v2"
    assert updates["chunks_count"] == 5
    assert updates["ingest_status"] == "completed"


@pytest.mark.asyncio
async def test_prepare_reingest_skips_without_prior_chunks() -> None:
    router = MagicMock(spec=QdrantRouter)
    router.clear_for_reingest = AsyncMock()
    session = AsyncMock()
    session.scalar.return_value = 0
    session.get.return_value = None

    await _prepare_reingest_if_needed(
        uuid.uuid4(),
        {"default_route": "both", "dedup": {"strategy": "skip_if_exists"}},
        router,
        session,
        {},
    )

    router.clear_for_reingest.assert_not_called()


@pytest.mark.asyncio
async def test_prepare_reingest_clears_existing_qdrant_for_same_doc() -> None:
    """Deprecated upfront delete path — still available for legacy callers/tests."""
    doc_id = uuid.uuid4()
    router = MagicMock(spec=QdrantRouter)
    router.clear_for_reingest = AsyncMock()
    session = AsyncMock()
    session.scalar.return_value = 2

    await _prepare_reingest_if_needed(
        doc_id,
        {"default_route": "both", "dedup": {"strategy": "skip_if_exists"}},
        router,
        session,
        {"factory_id": TEST_FACTORY, "document_category": "maintenance"},
    )

    router.clear_for_reingest.assert_awaited_once()
    assert router.clear_for_reingest.await_args.args[:2] == (doc_id, session)


@pytest.mark.asyncio
async def test_reingest_replaces_stale_qdrant_vectors(monkeypatch: pytest.MonkeyPatch) -> None:
    if not await _services_up():
        pytest.skip("Postgres or Qdrant unavailable")

    try:
        ensure_collection()
    except RuntimeError as exc:
        pytest.skip(f"Qdrant collection predates the bge-m3 1024-d upgrade; re-ingest required ({exc})")
    monkeypatch.setattr(
        "spark.ingestion.index.embedder.Embedder.get",
        lambda: FakeEmbedder(),
    )
    monkeypatch.setattr(
        "spark.ingestion.index.compute_pool.encode_dense_sync",
        lambda texts: [[0.1] * embedding_dimension() for _ in texts],
    )
    monkeypatch.setattr(
        "spark.ingestion.index.qdrant_writer.sparse_vectors_enabled",
        lambda: False,
    )

    parse_calls = {"n": 0}

    def fake_get_parser(_name: str) -> FakeManualParser:
        n = parse_calls["n"]
        parse_calls["n"] += 1
        return FakeManualParser(V1_CHUNKS if n == 0 else V2_CHUNKS)

    monkeypatch.setattr("spark.ingestion.stages.runner.get_parser", fake_get_parser)

    doc_id = uuid.uuid4()
    await _ensure_test_machine()
    await _register_doc(doc_id, revision="v1", title="Manual v1")

    router = QdrantRouter()
    dummy = Path("manual-v1.pdf")

    try:
        summary_v1 = await run_pipeline(
            doc_id=doc_id,
            file_path=dummy,
            document_type="machine_manual",
            document_context={
                "factory_id": TEST_FACTORY,
                "machine_id": TEST_MACHINE,
                "document_type": "machine_manual",
                "document_category": "knowledge",
                "language": "th",
                "revision": "v1",
                "source_file": "manual-v1.pdf",
                "title": "Manual v1",
            },
        )
        assert summary_v1.status == "completed"
        assert summary_v1.rows_ok == V1_CHUNKS
        assert await router.count_by_doc(doc_id, generation=1) == V1_CHUNKS

        async with AsyncSessionLocal() as session:
            pg_chunks = await session.scalar(
                select(func.count())
                .select_from(DocumentChunk)
                .where(
                    DocumentChunk.doc_id == doc_id,
                    DocumentChunk.ingest_generation == 1,
                )
            )
            doc = await session.get(Document, doc_id)
        assert pg_chunks == V1_CHUNKS
        assert doc is not None
        assert doc.active_ingest_generation == 1

        summary_v2 = await run_pipeline(
            doc_id=doc_id,
            file_path=Path("manual-v2.pdf"),
            document_type="machine_manual",
            document_context={
                "factory_id": TEST_FACTORY,
                "machine_id": TEST_MACHINE,
                "document_type": "machine_manual",
                "document_category": "knowledge",
                "language": "th",
                "revision": "v2",
                "source_file": "manual-v2.pdf",
                "title": "Manual v2",
            },
        )
        assert summary_v2.status == "completed"
        assert summary_v2.rows_ok == V2_CHUNKS
        assert await router.count_by_doc(doc_id, generation=2) == V2_CHUNKS

        async with AsyncSessionLocal() as session:
            pg_chunks = await session.scalar(
                select(func.count())
                .select_from(DocumentChunk)
                .where(
                    DocumentChunk.doc_id == doc_id,
                    DocumentChunk.ingest_generation == 2,
                )
            )
            doc = await session.get(Document, doc_id)
        assert pg_chunks == V2_CHUNKS
        assert doc is not None
        assert doc.revision == "v2"
        assert doc.active_ingest_generation == 2
        assert doc.source_file == "manual-v2.pdf"
        assert doc.title == "Manual v2"
        assert doc.chunks_count == V2_CHUNKS
    finally:
        await _cleanup_doc(doc_id)
