from __future__ import annotations

from spark.retrieval.token_counter import CharRatioCounter, TiktokenCounter


def test_tiktoken_counter_counts_non_empty() -> None:
    counter = TiktokenCounter()
    assert counter.count("hello world") >= 1


def test_char_ratio_counter_empty() -> None:
    counter = CharRatioCounter()
    assert counter.count("") == 0
    assert counter.count("abcd") >= 1
