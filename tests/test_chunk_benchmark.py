"""Unit tests for chunking benchmark helpers (issue #46)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from benchmark_chunking import (  # noqa: E402
    _mrr_and_hit,
    _pick_winner,
    ProfileScore,
)


def test_mrr_first_relevant_rank_one() -> None:
    chunks = ["unrelated intro", "Check cooling fan if temperature exceeds 80°C"]
    ranked = [1, 0]
    mrr, hit = _mrr_and_hit(ranked, chunks)
    assert mrr == 1.0
    assert hit == 1.0


def test_mrr_second_relevant_rank() -> None:
    chunks = ["unrelated", "also unrelated", "bearing maintenance every 5000 hours"]
    ranked = [0, 1, 2]
    mrr, hit = _mrr_and_hit(ranked, chunks)
    assert mrr == 1 / 3
    assert hit == 1.0


def test_pick_winner_excludes_current_baseline() -> None:
    scores = [
        ProfileScore("256", 256, 64, 10, 0.9, 1.0, "embedding"),
        ProfileScore("512", 512, 128, 5, 0.85, 1.0, "embedding"),
        ProfileScore("current_1200", 1200, 200, 2, 0.8, 0.9, "embedding"),
    ]
    assert _pick_winner(scores).name == "256"
