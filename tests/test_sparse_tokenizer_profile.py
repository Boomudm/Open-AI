from __future__ import annotations

import pytest

from spark.core.config import settings
from spark.core.llm_profile import load_llm_profile, sparse_tokenizer_model


def test_gemma_remote_sparse_tokenizer_resolves_to_hf_model() -> None:
    load_llm_profile.cache_clear()
    try:
        assert sparse_tokenizer_model("gemma_remote") == "BAAI/bge-m3"
    finally:
        load_llm_profile.cache_clear()


def test_demo_sparse_tokenizer_uses_embed_model() -> None:
    load_llm_profile.cache_clear()
    try:
        assert sparse_tokenizer_model("demo") == "BAAI/bge-m3"
    finally:
        load_llm_profile.cache_clear()


def test_sparse_tokenizer_gateway_alias_without_explicit_field(monkeypatch: pytest.MonkeyPatch) -> None:
    load_llm_profile.cache_clear()
    monkeypatch.setattr(settings, "llm_profile", "gemma_remote")
    try:
        assert sparse_tokenizer_model() == "BAAI/bge-m3"
    finally:
        load_llm_profile.cache_clear()
