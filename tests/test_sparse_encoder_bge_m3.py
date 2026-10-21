"""Phase 5 — BGE-M3 tokenizer sparse encoder tests."""

from __future__ import annotations

import builtins

import pytest

from spark.ingestion.index.sparse.bge_m3_sparse import (
    BgeM3SparseEncoder,
    _import_auto_tokenizer,
)


def test_bge_m3_sparse_encoder_id() -> None:
    encoder = BgeM3SparseEncoder()
    assert encoder.encoder_id == "bge_m3"


def test_bge_m3_encode_document_query_consistency() -> None:
    encoder = BgeM3SparseEncoder()
    text = "SKF-6205 bearing replacement every 5000 hours"
    doc_vec = encoder.encode_document(text)
    query_vec = encoder.encode_query(text)
    assert doc_vec.indices == query_vec.indices
    assert doc_vec.values == query_vec.values


def test_bge_m3_empty_text_returns_empty_sparse() -> None:
    encoder = BgeM3SparseEncoder()
    vec = encoder.encode_document("")
    assert vec.indices == []
    assert vec.values == []


def test_bge_m3_non_empty_text_has_token_indices() -> None:
    encoder = BgeM3SparseEncoder()
    vec = encoder.encode_document("พัดลมระบบทำความเย็น")
    assert vec.indices
    assert len(vec.indices) == len(vec.values)
    assert all(idx >= 0 for idx in vec.indices)


def test_import_auto_tokenizer_retries_partial_transformers_module(monkeypatch) -> None:
    """A worker that loses the transformers concurrent-import race must recover.

    transformers builds its namespace lazily, so a thread importing it while
    another is midway through raises ImportError. Reproduced on this box at 3-5
    failures per 8 concurrent threads; unretried it surfaced as a spurious
    service_unavailable on the first query after a restart.
    """
    real_import = builtins.__import__
    calls = {"n": 0}

    def flaky_import(name, *args, **kwargs):
        if name == "transformers":
            calls["n"] += 1
            if calls["n"] <= 2:  # the winner has not finished initialising yet
                raise ImportError("cannot import name 'AutoTokenizer' from 'transformers'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", flaky_import)
    monkeypatch.setattr("time.sleep", lambda _s: None)  # keep the test fast

    assert _import_auto_tokenizer() is not None
    assert calls["n"] == 3  # two failures, then success


def test_import_auto_tokenizer_gives_up_with_clear_error(monkeypatch) -> None:
    real_import = builtins.__import__

    def always_failing(name, *args, **kwargs):
        if name == "transformers":
            raise ImportError("cannot import name 'AutoTokenizer' from 'transformers'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", always_failing)
    monkeypatch.setattr("time.sleep", lambda _s: None)

    with pytest.raises(RuntimeError, match="AutoTokenizer unavailable after retries"):
        _import_auto_tokenizer()
