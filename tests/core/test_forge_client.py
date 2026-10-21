"""Unit tests for ForgeNode client response parsing."""

from __future__ import annotations

from spark.core.forge_client import _coerce_unit_score, _parse_rerank_scores


def test_parse_rerank_scores_openai_style() -> None:
    payload = {
        "results": [
            {"index": 1, "relevance_score": 0.12},
            {"index": 0, "relevance_score": 0.91},
        ]
    }
    scores = _parse_rerank_scores(payload, 2)
    assert scores == [0.91, 0.12]


def test_parse_rerank_scores_flat_list() -> None:
    payload = {"scores": [0.8, 0.2]}
    assert _parse_rerank_scores(payload, 2) == [0.8, 0.2]


def test_coerce_unit_score_logit() -> None:
    assert _coerce_unit_score(0.75) == 0.75
    assert 0.0 < _coerce_unit_score(2.0) < 1.0
