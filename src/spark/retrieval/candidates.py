"""Candidate identity, dedupe, and parent-context hydration."""

from __future__ import annotations

import hashlib
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from spark.db.models.docs import DocumentChunk
from spark.retrieval.models import RetrievedDoc


def retrieval_identity(doc: RetrievedDoc) -> tuple[Any, ...]:
    """Stable fusion key — (doc_id, chunk_id) when chunk_id is present."""
    payload = doc.payload
    chunk_id = payload.get("chunk_id")
    if chunk_id:
        return ("chunk", chunk_id)
    return (
        payload.get("doc_id"),
        payload.get("source_file"),
        payload.get("page"),
        payload.get("source_sheet"),
        payload.get("row_number"),
        payload.get("chunk_index"),
    )


def generation_context_for_doc(doc: RetrievedDoc) -> str:
    parent = str(doc.payload.get("parent_content") or "").strip()
    if parent:
        return parent
    return doc.page_content or ""


def doc_chunk_id(doc: RetrievedDoc) -> str:
    return str(doc.payload.get("chunk_id") or "").strip()


def group_docs_for_generation(docs: list[RetrievedDoc]) -> list[tuple[list[RetrievedDoc], str]]:
    # Group by parent id AND the actual context text. The ingest chunker has
    # assigned the same parent_chunk_id to children carrying DIFFERENT parent
    # windows (26/71 parents on this corpus — e.g. KUKA p.57 base spec table vs
    # p.58 4CAB variant table share one id). Grouping on id alone collapsed
    # them to group[0]'s text, so the model was handed a different table than
    # the one whose chunk_ids it was told to cite — and honestly answered
    # "not in the context". Distinct texts now stay distinct groups.
    groups: dict[tuple[str, str], list[RetrievedDoc]] = {}
    order: list[tuple[str, str]] = []
    for doc in docs:
        parent_id = str(doc.payload.get("parent_chunk_id") or doc_chunk_id(doc) or "")
        text_key = hashlib.md5(generation_context_for_doc(doc).encode()).hexdigest()
        key = (parent_id, text_key)
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(doc)

    result: list[tuple[list[RetrievedDoc], str]] = []
    for key in order:
        group = groups[key]
        context_text = generation_context_for_doc(group[0])
        result.append((group, context_text))
    return result


async def hydrate_parent_content_from_pg(
    session: AsyncSession,
    docs: list[RetrievedDoc],
) -> None:
    # First preference: each doc's OWN row carries the parent window that was
    # built around THAT child at ingest. Keying the lookup by parent_chunk_id
    # alone is unsafe — the chunker has assigned one parent id to different
    # parent windows (26/71 parents on this corpus), so a shared-id map handed
    # some children a sibling's window instead of their own.
    own_ids: set[uuid.UUID] = set()
    for doc in docs:
        if doc.payload.get("parent_content"):
            continue
        raw_cid = doc.payload.get("chunk_id")
        if not raw_cid:
            continue
        try:
            own_ids.add(uuid.UUID(str(raw_cid)))
        except (TypeError, ValueError):
            continue
    if own_ids:
        own_rows = (
            await session.execute(
                select(DocumentChunk.chunk_id, DocumentChunk.parent_content).where(
                    DocumentChunk.chunk_id.in_(own_ids),
                    DocumentChunk.parent_content.is_not(None),
                )
            )
        ).all()
        own_map = {
            str(chunk_id): str(parent_content).strip()
            for chunk_id, parent_content in own_rows
            if parent_content and str(parent_content).strip()
        }
        for doc in docs:
            cid = str(doc.payload.get("chunk_id") or "")
            if cid in own_map and not doc.payload.get("parent_content"):
                doc.payload["parent_content"] = own_map[cid]

    missing: set[uuid.UUID] = set()
    for doc in docs:
        if doc.payload.get("parent_content"):
            continue
        raw_pid = doc.payload.get("parent_chunk_id")
        if not raw_pid:
            continue
        try:
            missing.add(uuid.UUID(str(raw_pid)))
        except (TypeError, ValueError):
            continue
    if not missing:
        return

    parent_map: dict[str, str] = {}
    parent_rows = (
        await session.execute(
            select(
                DocumentChunk.chunk_id,
                DocumentChunk.parent_content,
                DocumentChunk.content,
            ).where(DocumentChunk.chunk_id.in_(missing))
        )
    ).all()
    for chunk_id, parent_content, content in parent_rows:
        text = str(parent_content or content or "").strip()
        if text:
            parent_map[str(chunk_id)] = text

    still_missing = {pid for pid in missing if str(pid) not in parent_map}
    if still_missing:
        child_rows = (
            await session.execute(
                select(DocumentChunk.parent_chunk_id, DocumentChunk.parent_content)
                .where(
                    DocumentChunk.parent_chunk_id.in_(still_missing),
                    DocumentChunk.parent_content.is_not(None),
                )
                .distinct()
            )
        ).all()
        for parent_id, parent_content in child_rows:
            if parent_id is None:
                continue
            key = str(parent_id)
            if key not in parent_map and parent_content:
                parent_map[key] = str(parent_content).strip()

    for doc in docs:
        pid = str(doc.payload.get("parent_chunk_id") or "")
        if pid and pid in parent_map:
            doc.payload["parent_content"] = parent_map[pid]
