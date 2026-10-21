"""Native-only ingest configs for general document types."""

from __future__ import annotations

from pathlib import Path

from spark.ingestion.config_loader import load_config
from spark.ingestion.document_type_resolver import detect_parser_for_path


def test_training_note_uses_native_word_parser() -> None:
    cfg = load_config("training_note")
    assert cfg.get("parser") == "word"
    assert cfg.get("default_route") == "qdrant"


def test_machine_manual_native_pdf_path() -> None:
    cfg = load_config("machine_manual")
    assert cfg.get("parser") == "pdf"
    assert detect_parser_for_path(Path("manual.pdf")) == "pdf"


def test_knowledge_document_native_text_path() -> None:
    cfg = load_config("knowledge_document")
    assert cfg.get("default_route") == "qdrant"
