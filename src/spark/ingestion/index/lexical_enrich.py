"""Index-time lexical enrichment for chunk mirror columns."""

from __future__ import annotations

from spark.retrieval.lexical.tokenize_industrial import extract_industrial_tokens
from spark.retrieval.lexical.tokenize_th import tokenize_th


def enrich_chunk_lexical(content: str) -> tuple[str, list[str]]:
    """Return Thai tokenized text and industrial boost tokens for a chunk."""
    text = (content or "").strip()
    if not text:
        return "", []
    # limit=48 (not the query-side default 24): a wiring-diagram device-index
    # chunk legitimately carries dozens of short device tags (K1, X1, M18 …),
    # and the extractor ranks longest-first, so under the default cap the short
    # tags — exactly the ones technicians query by — were the first casualties.
    return tokenize_th(text), extract_industrial_tokens(text, limit=48)
