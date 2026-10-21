"""Tests for lexical query normalization (Phase 6)."""

from spark.retrieval.lexical.query_build import extract_boosted_terms, normalize_lexical_query


def test_normalize_nfkc() -> None:
    assert normalize_lexical_query("  SKF\u20116205  ") == "SKF-6205"


def test_extract_boosted_terms_alarm_and_part() -> None:
    terms = extract_boosted_terms("Alarm E-204 on SKF-6205 for MC-001")
    joined = " ".join(terms)
    assert "E-204" in joined or "E204" in joined.upper()
    assert any("6205" in t for t in terms)
    assert any("MC" in t for t in terms)
