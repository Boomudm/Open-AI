"""Phase 6 lexical engine unit tests."""

from __future__ import annotations

from spark.ingestion.index.lexical_enrich import enrich_chunk_lexical
from spark.retrieval.lexical.query_build import build_lexical_query_parts
from spark.retrieval.lexical.rank import WEIGHT_SIMPLE_FTS, WEIGHT_THAI_FTS, WEIGHT_TRGM
from spark.retrieval.lexical.tokenize_industrial import extract_industrial_tokens
from spark.retrieval.lexical.tokenize_th import tokenize_th


def test_tokenize_th_produces_tokens() -> None:
    tokens = tokenize_th("ตรวจสอบพัดลมระบบทำความเย็น")
    assert tokens
    assert " " in tokens or len(tokens) > 3


def test_extract_industrial_tokens_part_and_alarm() -> None:
    tokens = extract_industrial_tokens("Replace SKF-6205 when alarm E-204 on MC-001")
    joined = " ".join(tokens)
    assert "6205" in joined
    assert "E-204" in joined or "E204" in joined.upper()


def test_extract_industrial_tokens_plc_tag() -> None:
    content_tokens = extract_industrial_tokens(
        "EcoRT_0 (BOOL, Input) at RES0.BELT_CALIB_SENSOR (no mapped target in this sheet)."
    )
    query_tokens = extract_industrial_tokens("RES0.BELT_CALIB_SENSOR เชื่อมกับอะไร")
    assert "RES0.BELT_CALIB_SENSOR" in content_tokens
    assert "RES0.BELT_CALIB_SENSOR" in query_tokens


def test_build_lexical_query_parts_splits_scripts() -> None:
    parts = build_lexical_query_parts("ตรวจ SKF-6205 E-204")
    assert parts["thai_text"] or parts["latin_text"]
    assert parts["boost_terms"]


def test_enrich_chunk_lexical() -> None:
    th, boost = enrich_chunk_lexical("Manual SKF-6205 ขั้นตอนซ่อม")
    assert th
    assert boost


def test_rank_weights_sum_to_one() -> None:
    assert abs(WEIGHT_THAI_FTS + WEIGHT_SIMPLE_FTS + WEIGHT_TRGM - 1.0) < 0.001
