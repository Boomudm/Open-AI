"""Tests for LLM profile loader."""

from __future__ import annotations

from spark.core.llm_profile import load_llm_profile


def test_load_demo_llm_profile() -> None:
    profile = load_llm_profile("demo")
    assert profile["provider"] == "ollama"
    assert profile["llm_model"] == "qwen2.5:3b-instruct"


def test_load_rag_th_profile() -> None:
    profile = load_llm_profile("rag_th")
    assert profile["llm_model"] == "qwen2.5:7b-instruct"
    assert profile["num_ctx"] == 8192
