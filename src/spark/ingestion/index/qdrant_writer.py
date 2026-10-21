from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any

from qdrant_client.models import PointStruct
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from spark.core.config import settings
from spark.core.llm_profile import embedding_dimension
from spark.core.logging import get_logger
from spark.core.qdrant import (
    DENSE_VECTOR_NAME,
    SPARSE_VECTOR_NAME,
    ensure_collection,
    get_async_qdrant_client,
    qdrant_retry_async,
    sparse_vectors_enabled,
)
from spark.core.qdrant_strategy import collection_for, get_strategy
from spark.db.models.docs import DocumentChunk
from spark.ingestion.chunking.context_header import embed_text_with_header
from spark.ingestion.embed_lineage import embed_lineage_for_text
from spark.ingestion.index.batch_policy import embed_batch_size
from spark.ingestion.index.compute_pool import IngestComputePool
from spark.ingestion.index.embedder import Embedder
from spark.ingestion.index.lexical_enrich import enrich_chunk_lexical
from spark.ingestion.index.sparse.encoder import get_sparse_encoder
from spark.contracts.qdrant_payload_schema import validate_qdrant_payload
from spark.contracts.rag_payload_contract import (
    PARSER_PG_ONLY_FIELDS,
    required_parser_fields_for_strategy,
)
from spark.ingestion.parsers.base import ParsedRecord

log = get_logger(__name__)

INGEST_VERSION = "v3"


def _sanitize_text(text: str | None) -> str | None:
    if text is None:
        return None
    return text.replace("\x00", "")


def _normalized_tag_path(value: Any) -> str | None:
    """Lowercased PLC/IO tag path for case-insensitive exact-match filtering."""
    text = str(value).strip().lower() if value is not None else ""
    return text or None

# Default denylist — large or PG-only parser fields never indexed to Qdrant.
DEFAULT_PAYLOAD_FIELD_EXCLUSIONS = frozenset(PARSER_PG_ONLY_FIELDS)


def _optional_uuid(value: Any) -> uuid.UUID | None:
    if value is None:
        return None
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError):
        return None


def _epoch_day(date_value: Any) -> int | None:
    if date_value is None:
        return None
    try:
        if hasattr(date_value, "toordinal"):
            return date_value.toordinal() - datetime(1970, 1, 1).toordinal()
    except Exception:
        return None
    return None


class QdrantWriter:
    """Embed records + upsert into Qdrant + mirror chunk rows to PostgreSQL."""

    def __init__(self, batch_size: int | None = None) -> None:
        self.batch_size = batch_size or embed_batch_size()
        self.embedder = Embedder.get()
        self.sparse_encoder = get_sparse_encoder()
        self._compute_pool = IngestComputePool.get()

    async def write(
        self,
        records: list[ParsedRecord],
        doc_id: uuid.UUID,
        config: dict[str, Any],
        document_context: dict[str, Any],
        session: AsyncSession,
        *,
        ingest_generation: int = 1,
        allocated_chunk_ids: set[uuid.UUID] | None = None,
    ) -> int:
        if not records:
            return 0
        if allocated_chunk_ids is None:
            allocated_chunk_ids = set()

        qdrant_cfg = config.get("qdrant") or {}
        if get_strategy() == "single":
            collection = qdrant_cfg.get("collection") or collection_for(
                document_context.get("factory_id"),
                document_context.get("document_category"),
            )
        else:
            collection = collection_for(
                document_context.get("factory_id"),
                document_context.get("document_category"),
            )
        payload_exclusions: set[str] = set(qdrant_cfg.get("payload_field_exclusions") or [])
        payload_exclusions |= DEFAULT_PAYLOAD_FIELD_EXCLUSIONS
        chunking_strategy = str((config.get("chunking") or {}).get("strategy") or "")
        required_parser_fields = required_parser_fields_for_strategy(chunking_strategy)
        # Excel-only strategies (table_row) require sheet/row citation fields —
        # but a document type configured for Excel can still receive a PDF via
        # parser: auto (real case: mapping_diagram.pdf under io_mapping). Those
        # records are chunked by the fallback strategy (see chunk_blocks) and
        # carry page locators instead; holding them to the sheet contract sent
        # the whole document to DLQ. ExcelParser stamps source_sheet on every
        # record, so its presence is reliable provenance.
        from spark.ingestion.chunk.types import EXCEL_ONLY_CHUNK_STRATEGIES

        strategy_is_excel_only = chunking_strategy in EXCEL_ONLY_CHUNK_STRATEGIES
        default_required_fields = required_parser_fields_for_strategy(None)
        client = get_async_qdrant_client()
        now_epoch = int(datetime.now(tz=timezone.utc).timestamp())
        embed_profile = self.embedder.embed_profile()
        config_hash = str(document_context.get("config_hash") or "")

        from spark.services.document_access_service import restricted_position_ids_for_docs

        restricted_map = await restricted_position_ids_for_docs(session, [doc_id])
        restricted_ids = restricted_map.get(doc_id)
        restricted_position_payload = (
            [str(position_id) for position_id in restricted_ids] if restricted_ids else None
        )

        total_written = 0
        for batch_start in range(0, len(records), self.batch_size):
            batch = records[batch_start : batch_start + self.batch_size]
            embed_inputs: list[str] = []
            for rec in batch:
                raw = (rec.text_for_embedding or rec.payload.get("page_content") or "").strip()
                embed_inputs.append(embed_text_with_header(raw, document_context, rec.payload))
            sparse_enabled = sparse_vectors_enabled() and self.sparse_encoder.encoder_id != "none"
            raw_contents = [
                (rec.payload.get("page_content") or rec.text_for_embedding or "").strip() for rec in batch
            ]
            if sparse_enabled:
                vectors, sparse_vectors = await asyncio.gather(
                    self._compute_pool.encode_dense_batch(embed_inputs),
                    self._compute_pool.encode_sparse_batch(raw_contents),
                )
            else:
                vectors = await self._compute_pool.encode_dense_batch(embed_inputs)
                sparse_vectors = []
            if sparse_enabled and len(sparse_vectors) != len(batch):
                raise ValueError(
                    f"sparse batch size mismatch for doc {doc_id}: "
                    f"got {len(sparse_vectors)} expected {len(batch)}"
                )
            # Thai word segmentation (pythainlp newmm) is CPU-bound; running it
            # inline per record blocked the worker's event loop for the whole
            # batch. Compute the batch in a thread alongside nothing else the
            # loop needs, then index by position below.
            lexical_enrichment = await asyncio.get_running_loop().run_in_executor(
                None, lambda: [enrich_chunk_lexical(content) for content in raw_contents]
            )
            if vectors:
                expected_dim = embed_profile.dimension
                for offset, vec in enumerate(vectors):
                    if len(vec) != expected_dim:
                        raise ValueError(
                            f"embedding dimension mismatch for doc {doc_id} chunk "
                            f"{batch_start + offset}: got {len(vec)}, expected {expected_dim} "
                            f"(LLM_PROFILE={settings.llm_profile!r}). Aborting upsert to avoid "
                            "corrupting the vector store; re-ingest after embedding changes."
                        )
                ensure_collection(collection, vector_size=expected_dim)

            points: list[PointStruct] = []
            chunks_to_insert: list[DocumentChunk] = []

            for rec_index, (rec, vector, embed_input) in enumerate(
                zip(batch, vectors, embed_inputs, strict=True)
            ):
                record_required_fields = required_parser_fields
                if strategy_is_excel_only and "source_sheet" not in rec.payload:
                    record_required_fields = default_required_fields
                missing = record_required_fields - set(rec.payload.keys())
                if missing:
                    raise ValueError(
                        f"missing parser payload fields for strategy {chunking_strategy!r}: "
                        f"{sorted(missing)} doc={doc_id}"
                    )
                chunk_id = _optional_uuid(rec.payload.get("chunk_id")) or uuid.uuid4()
                if chunk_id in allocated_chunk_ids:
                    chunk_id = uuid.uuid4()
                allocated_chunk_ids.add(chunk_id)
                raw_content = (rec.payload.get("page_content") or rec.text_for_embedding or "").strip()
                parent_content = rec.payload.get("parent_content")
                lineage = embed_lineage_for_text(
                    embed_input,
                    profile=embed_profile,
                    config_hash=config_hash,
                )
                th_tokenized, boost_tokens = lexical_enrichment[rec_index]
                base_payload: dict[str, Any] = {
                    "doc_id": str(doc_id),
                    "chunk_id": str(chunk_id),
                    "chunk_index": rec.payload.get("chunk_index", 0),
                    "page": rec.payload.get("page"),
                    "source_sheet": rec.payload.get("source_sheet"),
                    "row_number": rec.payload.get("row_number"),
                    "extraction_source": rec.payload.get("extraction_source"),
                    "factory_id": document_context.get("factory_id"),
                    "machine_id": document_context.get("machine_id"),
                    "component_id": rec.payload.get("component_id") or document_context.get("component_id"),
                    "document_category": document_context.get("document_category"),
                    "document_type": document_context.get("document_type"),
                    "language": document_context.get("language", "th"),
                    "revision": document_context.get("revision"),
                    "revision_sort_key": document_context.get("revision_sort_key"),
                    "drawing_no": rec.payload.get("drawing_no") or document_context.get("drawing_no"),
                    "source_file": document_context.get("source_file"),
                    "title": document_context.get("title"),
                    "effective_date": _epoch_day(document_context.get("effective_date")),
                    "expiry_date": _epoch_day(document_context.get("expiry_date")),
                    "ingested_at": now_epoch,
                    "ingest_version": INGEST_VERSION,
                    "ingest_generation": ingest_generation,
                    "embed_model_id": lineage["embed_model_id"],
                    "embed_model": lineage["embed_model"],
                    "embed_model_version": lineage["embed_model_version"],
                    "embed_provider": lineage["embed_provider"],
                    "embed_dimension": lineage["embed_dimension"],
                    "config_hash": lineage["config_hash"],
                    "content_hash": lineage["content_hash"],
                    "chunk_schema_version": lineage["chunk_schema_version"],
                    "sparse_encoder_id": self.sparse_encoder.encoder_id,
                    "page_content": raw_content,
                    "parent_chunk_id": rec.payload.get("parent_chunk_id"),
                    "parent_index": rec.payload.get("parent_index"),
                    "child_index_in_parent": rec.payload.get("child_index_in_parent"),
                    "chunk_level": rec.payload.get("chunk_level"),
                    "has_tables": rec.payload.get("has_tables"),
                    "extraction_confidence": rec.payload.get("extraction_confidence"),
                    "section_path": rec.payload.get("section_path"),
                    "retrieval_enabled": not bool(rec.payload.get("_policy_quarantine")),
                    "boost_tokens": boost_tokens or None,
                    "needs_review": rec.payload.get("needs_review"),
                    # Stored lowercased: these fields exist solely for the
                    # exact-match tag lookup (build_exact_tag_filter), which
                    # must be case-insensitive — technicians type tags from
                    # memory and the sheets mix cases ("RES0.Belt_Control").
                    # Display text lives in page_content, never here.
                    "src_path": _normalized_tag_path(rec.payload.get("src_path")),
                    "tgt_path": _normalized_tag_path(rec.payload.get("tgt_path")),
                }
                if restricted_position_payload:
                    base_payload["restricted_position_ids"] = restricted_position_payload

                for excluded in payload_exclusions:
                    base_payload.pop(excluded, None)

                payload = validate_qdrant_payload(base_payload)

                point_vector: dict[str, Any] = {DENSE_VECTOR_NAME: vector}
                if sparse_enabled:
                    sparse_vec = sparse_vectors[rec_index]
                    if sparse_vec.indices:
                        point_vector[SPARSE_VECTOR_NAME] = sparse_vec
                point_kwargs: dict[str, Any] = {
                    "id": str(chunk_id),
                    "vector": point_vector,
                    "payload": payload,
                }
                points.append(PointStruct(**point_kwargs))
                chunks_to_insert.append(
                    DocumentChunk(
                        chunk_id=chunk_id,
                        doc_id=doc_id,
                        qdrant_point_id=chunk_id,
                        chunk_index=int(rec.payload.get("chunk_index", 0) or 0),
                        page=rec.payload.get("page"),
                        char_count=len(raw_content),
                        content=raw_content,
                        payload=payload,
                        ingest_generation=ingest_generation,
                        parent_chunk_id=_optional_uuid(rec.payload.get("parent_chunk_id")),
                        chunk_level=rec.payload.get("chunk_level"),
                        parent_content=str(parent_content).strip() if parent_content else None,
                        content_hash=str(lineage["content_hash"]),
                        embed_model=str(lineage["embed_model"]),
                        embed_model_version=str(lineage["embed_model_version"]),
                        chunk_schema_version=int(lineage["chunk_schema_version"]),
                        content_th_tokenized=th_tokenized or None,
                        boost_tokens=boost_tokens or None,
                    )
                )

            # Idempotent insert: delete any stale rows with the same chunk_ids
            # before inserting.  chunk_ids are stable UUID5 values derived from
            # (doc_id, section_path, leaf_index), so a retry for the same
            # document content produces identical IDs.  Without this guard,
            # partial batches committed in a previous failed attempt trigger
            # UniqueViolationError on the document_chunks primary key.
            if chunks_to_insert:
                from sqlalchemy import delete as sa_delete

                stale_ids = [c.chunk_id for c in chunks_to_insert]
                await session.execute(
                    sa_delete(DocumentChunk).where(DocumentChunk.chunk_id.in_(stale_ids))
                )
            for chunk in chunks_to_insert:
                chunk.content = _sanitize_text(chunk.content)
                chunk.parent_content = _sanitize_text(chunk.parent_content)
            for chunk in chunks_to_insert:
                chunk.sync_status = "pending"
            session.add_all(chunks_to_insert)
            await session.flush()
            batch_chunk_ids = [c.chunk_id for c in chunks_to_insert]
            try:
                await qdrant_retry_async(
                    lambda: client.upsert(collection_name=collection, points=points, wait=True)
                )
                if batch_chunk_ids:
                    await session.execute(
                        update(DocumentChunk)
                        .where(DocumentChunk.chunk_id.in_(batch_chunk_ids))
                        .values(sync_status="synced")
                    )
            except Exception:
                log.error(
                    "qdrant_upsert_failed_outbox",
                    doc_id=str(doc_id),
                    batch_size=len(batch_chunk_ids),
                )
                raise
            total_written += len(points)

        log.info(
            "qdrant_writer_write",
            doc_id=str(doc_id),
            points=total_written,
            ingest_generation=ingest_generation,
        )
        return total_written

    async def reupsert_from_pg_mirror(
        self,
        session: AsyncSession,
        doc_id: uuid.UUID,
        *,
        generation: int,
        collection: str | None,
        document_context: dict[str, Any],
    ) -> int:
        """Re-embed and upsert PG mirror rows when Qdrant is missing points."""
        rows = (
            await session.execute(
                select(DocumentChunk).where(
                    DocumentChunk.doc_id == doc_id,
                    DocumentChunk.ingest_generation == generation,
                )
            )
        ).scalars().all()
        if not rows:
            return 0

        client = get_async_qdrant_client()
        coll = collection or settings.qdrant_collection
        texts = [row.content or "" for row in rows]
        sparse_enabled = sparse_vectors_enabled() and self.sparse_encoder.encoder_id != "none"
        if sparse_enabled:
            vectors, sparse_vectors = await asyncio.gather(
                self._compute_pool.encode_dense_batch(texts),
                self._compute_pool.encode_sparse_batch(texts),
            )
        else:
            vectors = await self._compute_pool.encode_dense_batch(texts)
            sparse_vectors = []
        ensure_collection(coll, vector_size=len(vectors[0]) if vectors else embedding_dimension())

        points: list[PointStruct] = []
        for row_index, (row, vector) in enumerate(zip(rows, vectors, strict=True)):
            payload = dict(row.payload or {})
            payload.setdefault("doc_id", str(doc_id))
            payload.setdefault("chunk_id", str(row.chunk_id))
            payload.setdefault("ingest_generation", generation)
            point_vector: dict[str, Any] = {DENSE_VECTOR_NAME: vector}
            if sparse_enabled:
                sparse_vec = sparse_vectors[row_index]
                if sparse_vec.indices:
                    point_vector[SPARSE_VECTOR_NAME] = sparse_vec
            payload.setdefault("sparse_encoder_id", self.sparse_encoder.encoder_id)
            points.append(
                PointStruct(
                    id=str(row.qdrant_point_id),
                    vector=point_vector,
                    payload=payload,
                )
            )

        await qdrant_retry_async(
            lambda: client.upsert(collection_name=coll, points=points, wait=True)
        )
        log.info(
            "qdrant_writer_reupsert_mirror",
            doc_id=str(doc_id),
            generation=generation,
            points=len(points),
        )
        return len(points)

    async def delete_by_doc(self, doc_id: uuid.UUID, collection: str | None = None) -> None:
        from qdrant_client.models import FieldCondition, Filter, MatchValue

        client = get_async_qdrant_client()
        coll = collection or settings.qdrant_collection
        await qdrant_retry_async(
            lambda: client.delete(
                collection_name=coll,
                points_selector=Filter(
                    must=[FieldCondition(key="doc_id", match=MatchValue(value=str(doc_id)))]
                ),
                wait=True,
            )
        )

    async def delete_by_doc_generation(
        self,
        doc_id: uuid.UUID,
        *,
        generation: int,
        collection: str | None = None,
    ) -> None:
        from qdrant_client.models import FieldCondition, Filter, MatchValue

        client = get_async_qdrant_client()
        coll = collection or settings.qdrant_collection
        await qdrant_retry_async(
            lambda: client.delete(
                collection_name=coll,
                points_selector=Filter(
                    must=[
                        FieldCondition(key="doc_id", match=MatchValue(value=str(doc_id))),
                        FieldCondition(key="ingest_generation", match=MatchValue(value=generation)),
                    ]
                ),
                wait=True,
            )
        )

    async def delete_by_doc_except_generation(
        self,
        doc_id: uuid.UUID,
        *,
        keep_generation: int,
        collection: str | None = None,
    ) -> None:
        from qdrant_client.models import FieldCondition, Filter, MatchValue

        client = get_async_qdrant_client()
        coll = collection or settings.qdrant_collection
        await qdrant_retry_async(
            lambda: client.delete(
                collection_name=coll,
                points_selector=Filter(
                    must=[FieldCondition(key="doc_id", match=MatchValue(value=str(doc_id)))],
                    must_not=[
                        FieldCondition(
                            key="ingest_generation",
                            match=MatchValue(value=keep_generation),
                        )
                    ],
                ),
                wait=True,
            )
        )

    async def count_by_doc(
        self,
        doc_id: uuid.UUID,
        collection: str | None = None,
        *,
        generation: int | None = None,
    ) -> int:
        from qdrant_client.models import FieldCondition, Filter, MatchValue

        client = get_async_qdrant_client()
        must = [FieldCondition(key="doc_id", match=MatchValue(value=str(doc_id)))]
        if generation is not None:
            must.append(
                FieldCondition(key="ingest_generation", match=MatchValue(value=generation))
            )
        coll = collection or settings.qdrant_collection
        result = await qdrant_retry_async(
            lambda: client.count(
                collection_name=coll,
                count_filter=Filter(must=must),
                exact=True,
            )
        )
        return int(result.count)

    async def set_retrieval_enabled_for_doc(
        self,
        doc_id: uuid.UUID,
        *,
        enabled: bool,
        collection: str | None = None,
    ) -> None:
        from qdrant_client.models import FieldCondition, Filter, MatchValue

        client = get_async_qdrant_client()
        coll = collection or settings.qdrant_collection
        await qdrant_retry_async(
            lambda: client.set_payload(
                collection_name=coll,
                payload={"retrieval_enabled": enabled},
                points=Filter(
                    must=[FieldCondition(key="doc_id", match=MatchValue(value=str(doc_id)))]
                ),
                wait=True,
            )
        )

    async def clear_for_reingest(
        self, doc_id: uuid.UUID, session: AsyncSession, collection: str | None = None
    ) -> None:
        from sqlalchemy import delete

        await self.delete_by_doc(doc_id, collection=collection)
        await session.execute(delete(DocumentChunk).where(DocumentChunk.doc_id == doc_id))


QdrantRouter = QdrantWriter
