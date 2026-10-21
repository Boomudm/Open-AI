"""Integration tests for per_factory Qdrant sharding (issue #60)."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
import pytest

from spark.core.config import settings
from spark.core.database import AsyncSessionLocal
from spark.core.llm_profile import embedding_dimension
from spark.core.qdrant import ensure_collection
from spark.core.qdrant_strategy import collection_for
from spark.db.models.docs import Document
from spark.db.models.org import Factory, Machine
from spark.ingestion.parsers.base import ParsedRecord
from spark.ingestion.pipeline import run_pipeline
from spark.ingestion.index.qdrant_writer import QdrantRouter
from spark.services.rag_service import RAGFilter, rag_service

F01_MACHINE = "SHARD-F01"
F02_MACHINE = "SHARD-F02"
F01_MARKER = "UNIQUE-F01-SHARD-MARKER-XYZ"
F02_MARKER = "UNIQUE-F02-SHARD-MARKER-XYZ"


class _FakeSyncEmbeddings:
    """Sync langchain-style shim used by batch_encode.encode_dense_sync."""

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[0.1] * embedding_dimension() for _ in texts]

    def embed_query(self, text: str) -> list[float]:
        return [0.1] * embedding_dimension()


class FakeEmbedder:
    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[0.1] * embedding_dimension() for _ in texts]

    async def embed_query(self, text: str) -> list[float]:
        return [0.1] * embedding_dimension()

    def _embeddings(self) -> _FakeSyncEmbeddings:
        return _FakeSyncEmbeddings()

    def embed_profile(self):
        from spark.ingestion.embed_profile import EmbedProfile

        return EmbedProfile(
            model_id="test-embed",
            provider="ollama",
            dimension=embedding_dimension(),
            llm_profile="test",
        )


class MarkerParser:
    def __init__(self, marker: str) -> None:
        self.marker = marker

    async def parse(self, file_path: Path, config: dict[str, Any]) -> AsyncIterator[ParsedRecord]:
        yield ParsedRecord(
            route="qdrant",
            payload={
                "page_content": self.marker,
                "chunk_index": 0,
                "page": 1,
                # chunk schema v2 (page_aware_parent_child) requires these.
                "chunk_level": "child",
                "parent_chunk_id": f"{self.marker}-parent-0",
                "parent_content": f"{self.marker} parent context",
            },
            text_for_embedding=self.marker,
        )


async def _services_up() -> bool:
    try:
        from spark.core.qdrant import get_async_qdrant_client

        client = get_async_qdrant_client()
        await client.get_collections()
        async with AsyncSessionLocal() as session:
            from sqlalchemy import select

            await session.execute(select(1))
        return True
    except Exception:
        return False


async def _ensure_machines() -> None:
    async with AsyncSessionLocal() as session:
        for fid, mid, name in [
            ("F-01", F01_MACHINE, "Shard Test F01"),
            ("F-02", F02_MACHINE, "Shard Test F02"),
        ]:
            if await session.get(Factory, fid) is None:
                session.add(Factory(factory_id=fid, factory_name=f"Plant {fid}", location=fid))
            if await session.get(Machine, mid) is None:
                session.add(
                    Machine(
                        machine_id=mid,
                        factory_id=fid,
                        machine_name=name,
                        machine_type="motor",
                    )
                )
        await session.commit()


async def _register_doc(doc_id: uuid.UUID, *, factory_id: str, machine_id: str, marker: str) -> None:
    async with AsyncSessionLocal() as session:
        session.add(
            Document(
                doc_id=doc_id,
                factory_id=factory_id,
                machine_id=machine_id,
                document_category="knowledge",
                document_type="machine_manual",
                title=f"Shard test {factory_id}",
                revision="v1",
                source_file=f"{factory_id}.pdf",
                ingest_status="pending",
            )
        )
        await session.commit()


async def _cleanup_doc(doc_id: uuid.UUID, factory_id: str) -> None:
    router = QdrantRouter()
    coll = collection_for(factory_id, "knowledge")
    try:
        await router.delete_by_doc(doc_id, collection=coll)
    except Exception:
        pass
    async with AsyncSessionLocal() as session:
        doc = await session.get(Document, doc_id)
        if doc:
            await session.delete(doc)
            await session.commit()


@pytest.mark.asyncio
async def test_per_factory_ingest_isolates_collections(monkeypatch: pytest.MonkeyPatch) -> None:
    if not await _services_up():
        pytest.skip("Postgres or Qdrant unavailable")

    monkeypatch.setattr(settings, "qdrant_shard_strategy", "per_factory")
    monkeypatch.setattr(
        "spark.ingestion.index.embedder.Embedder.get",
        lambda: FakeEmbedder(),
    )
    monkeypatch.setattr(
        "spark.services.rag_service.Embedder.get",
        lambda: FakeEmbedder(),
    )

    parser_map = {
        F01_MARKER: MarkerParser(F01_MARKER),
        F02_MARKER: MarkerParser(F02_MARKER),
    }

    call_idx = {"n": 0}

    def rotating_parser(_name: str) -> MarkerParser:
        marker = F01_MARKER if call_idx["n"] == 0 else F02_MARKER
        call_idx["n"] += 1
        return parser_map[marker]

    # The staged runner binds get_parser at import time — patch it there, not
    # on the legacy pipeline module.
    monkeypatch.setattr("spark.ingestion.stages.runner.get_parser", rotating_parser)

    await _ensure_machines()
    doc_f01 = uuid.uuid4()
    doc_f02 = uuid.uuid4()
    coll_f01 = collection_for("F-01", "knowledge")
    coll_f02 = collection_for("F-02", "knowledge")
    try:
        ensure_collection(coll_f01)
        ensure_collection(coll_f02)
    except RuntimeError as exc:
        pytest.skip(f"Qdrant collection predates the bge-m3 1024-d upgrade; re-ingest required ({exc})")

    router = QdrantRouter()
    try:
        await _register_doc(doc_f01, factory_id="F-01", machine_id=F01_MACHINE, marker=F01_MARKER)
        await _register_doc(doc_f02, factory_id="F-02", machine_id=F02_MACHINE, marker=F02_MARKER)

        summary1 = await run_pipeline(
            doc_id=doc_f01,
            file_path=Path("f01.pdf"),
            document_type="machine_manual",
            document_context={
                "factory_id": "F-01",
                "machine_id": F01_MACHINE,
                "document_type": "machine_manual",
                "document_category": "knowledge",
                "language": "th",
                "revision": "v1",
                "source_file": "f01.pdf",
                "title": "F01 manual",
            },
        )
        assert summary1.status == "completed"
        assert await router.count_by_doc(doc_f01, collection=coll_f01) == 1
        assert await router.count_by_doc(doc_f01, collection=coll_f02) == 0

        summary2 = await run_pipeline(
            doc_id=doc_f02,
            file_path=Path("f02.pdf"),
            document_type="machine_manual",
            document_context={
                "factory_id": "F-02",
                "machine_id": F02_MACHINE,
                "document_type": "machine_manual",
                "document_category": "knowledge",
                "language": "th",
                "revision": "v1",
                "source_file": "f02.pdf",
                "title": "F02 manual",
            },
        )
        assert summary2.status == "completed"
        assert await router.count_by_doc(doc_f02, collection=coll_f02) == 1
        assert await router.count_by_doc(doc_f02, collection=coll_f01) == 0

        hits_f01 = await rag_service._retrieve(
            query=F01_MARKER,
            rf=RAGFilter(factory_id="F-01", machine_id=F01_MACHINE, only_active=False),
            top_k=5,
        )
        markers_f01 = {h.page_content for h in hits_f01}
        assert F01_MARKER in markers_f01
        assert F02_MARKER not in markers_f01

        hits_f02 = await rag_service._retrieve(
            query=F02_MARKER,
            rf=RAGFilter(factory_id="F-02", machine_id=F02_MACHINE, only_active=False),
            top_k=5,
        )
        markers_f02 = {h.page_content for h in hits_f02}
        assert F02_MARKER in markers_f02
        assert F01_MARKER not in markers_f02
    finally:
        await _cleanup_doc(doc_f01, "F-01")
        await _cleanup_doc(doc_f02, "F-02")
