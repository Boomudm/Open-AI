"""Tests for structured document revision parsing (Phase 10)."""

from __future__ import annotations

import uuid

from spark.services.document_revision import parse_revision, revision_sort_key_from_label
from spark.retrieval.models import RetrievedDoc
from spark.services.rag_service import RAGService


def test_v10_ranks_above_v2() -> None:
    v2_key, _ = parse_revision("v2")
    v10_key, _ = parse_revision("v10")
    assert v10_key > v2_key


def test_revision_sort_key_supports_date_and_iso() -> None:
    date_key, _ = parse_revision("2024-03-01")
    iso_key, _ = parse_revision("ISO-2024.1")
    assert date_key == 20240301
    assert iso_key == 2024001


def test_filter_latest_revision_uses_sort_key_not_string() -> None:
    doc_id = str(uuid.uuid4())

    def _doc(revision: str, sort_key: int | None = None) -> RetrievedDoc:
        payload = {
            "doc_id": doc_id,
            "revision": revision,
            "chunk_id": str(uuid.uuid4()),
        }
        if sort_key is not None:
            payload["revision_sort_key"] = sort_key
        return RetrievedDoc(page_content="text", score=0.5, vector_score=0.5, payload=payload)

    svc = RAGService()
    older = _doc("v2", parse_revision("v2")[0])
    newer = _doc("v10", parse_revision("v10")[0])
    filtered = svc._filter_latest_revision([older, newer])
    assert len(filtered) == 1
    assert filtered[0].payload["revision"] == "v10"


def test_revision_sort_key_from_label_none_for_empty() -> None:
    assert revision_sort_key_from_label(None) is None
    assert revision_sort_key_from_label("") is None
