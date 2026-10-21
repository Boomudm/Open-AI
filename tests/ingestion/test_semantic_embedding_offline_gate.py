"""Phase 5 — semantic embedding gated off ingest hot path."""

from __future__ import annotations

import sys

from spark.ingestion.chunk.registry import chunk_text


def test_semantic_embedding_requires_offline_only() -> None:
    chunks = chunk_text(
        "First sentence. Second sentence. Third sentence.",
        chunk_size=200,
        chunk_overlap=20,
        strategy="semantic",
        semantic_breakpoint_threshold=0.5,
        offline_only=False,
    )
    assert chunks


def test_parse_hot_path_does_not_import_sentence_transformers() -> None:
    before = "sentence_transformers" in sys.modules
    chunk_text(
        "Paragraph one.\n\nParagraph two with more detail.",
        strategy="recursive",
        chunk_size=400,
        chunk_overlap=50,
    )
    if not before:
        assert "sentence_transformers" not in sys.modules
