"""Contract: Phase 6 lexical engine — postgres_thai_v3."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RETRIEVAL_DIR = ROOT / "src" / "spark" / "retrieval"


def test_no_client_scroll_in_rag_retrieval() -> None:
    engine_py = RETRIEVAL_DIR / "engine.py"
    source = engine_py.read_text(encoding="utf-8")
    assert "client.scroll" not in source
    assert "_retrieve_qdrant_lexical_candidates" not in source


def test_lexical_package_exports_factory() -> None:
    from spark.retrieval.lexical import RetrievalLexicalEngine, get_lexical_retriever, retrieve_lexical_candidates
    from spark.retrieval.lexical.postgres_thai_v3 import PostgresThaiV3LexicalEngine

    assert isinstance(get_lexical_retriever("postgres_thai_v3"), PostgresThaiV3LexicalEngine)
    assert callable(retrieve_lexical_candidates)
    assert RetrievalLexicalEngine.__args__ == ("postgres_thai_v3",)  # type: ignore[attr-defined]


def test_postgres_v2_module_removed() -> None:
    lexical_dir = ROOT / "src" / "spark" / "retrieval" / "lexical"
    assert not (lexical_dir / "postgres_v2.py").exists()
    assert not (lexical_dir / "legacy_postgres.py").exists()
    assert not (lexical_dir / "opensearch.py").exists()


def test_retrieval_lexical_package_exists() -> None:
    assert (ROOT / "src" / "spark" / "retrieval" / "lexical" / "postgres_thai_v3.py").is_file()
