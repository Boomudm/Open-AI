"""Lexical query normalization and tsquery construction."""

from __future__ import annotations

import re
import unicodedata

from spark.retrieval.lexical.tokenize_industrial import extract_industrial_tokens
from spark.retrieval.lexical.tokenize_th import split_thai_latin_segments

_UNICODE_DASHES = re.compile(r"[\u2010\u2011\u2012\u2013\u2014\u2015\u2212\uFE58\uFE63\uFF0D]")


def normalize_lexical_query(query: str) -> str:
    """NFKC normalize for stable Thai/Latin matching."""
    normalized = unicodedata.normalize("NFKC", (query or "").strip())
    return _UNICODE_DASHES.sub("-", normalized)


def build_lexical_query_parts(query: str) -> dict[str, str | list[str]]:
    """Split query into Thai, Latin/simple FTS, trgm, and boost token lists."""
    normalized = normalize_lexical_query(query)
    thai_text, latin_text = split_thai_latin_segments(normalized)
    boost_terms = extract_industrial_tokens(normalized)
    trgm_text = latin_text or normalized
    return {
        "normalized": normalized,
        "thai_text": thai_text,
        "latin_text": latin_text,
        "trgm_text": trgm_text,
        "boost_terms": boost_terms,
    }


def extract_boosted_terms(query: str, *, limit: int = 12) -> list[str]:
    """Backward-compatible alias used by legacy callers."""
    return extract_industrial_tokens(normalize_lexical_query(query), limit=limit)
