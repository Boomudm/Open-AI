"""Convex rank merge for dual FTS + trgm + boost."""

from __future__ import annotations

from sqlalchemy import func

# Default weights from Phase 6 blueprint (tune via eval_lexical_baseline.yaml).
WEIGHT_THAI_FTS = 0.55
WEIGHT_SIMPLE_FTS = 0.25
WEIGHT_TRGM = 0.20
BOOST_TOKEN_WEIGHT = 2.0


def combined_lexical_rank(
    *,
    thai_fts_rank,
    simple_fts_rank,
    trgm_score,
    boost_hits: int = 0,
):
    """SQL expression for weighted lexical score."""
    base = (
        (func.coalesce(thai_fts_rank, 0) * WEIGHT_THAI_FTS)
        + (func.coalesce(simple_fts_rank, 0) * WEIGHT_SIMPLE_FTS)
        + (func.coalesce(trgm_score, 0) * WEIGHT_TRGM)
    )
    if boost_hits:
        return base + (boost_hits * BOOST_TOKEN_WEIGHT)
    return base
