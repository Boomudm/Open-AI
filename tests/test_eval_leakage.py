from __future__ import annotations

from spark.eval.leakage import (
    char_shingles,
    extract_questions,
    find_leakage,
    jaccard,
    normalize_question,
    question_fingerprint,
)


def test_normalize_strips_punctuation_and_case() -> None:
    assert normalize_question("  MC-001:  ร้อน??? ") == "mc 001 ร้อน"


def test_fingerprint_stable_across_cosmetic_differences() -> None:
    assert question_fingerprint("MC-001 ร้อน!") == question_fingerprint("mc-001   ร้อน")


def test_find_leakage_detects_exact_overlap() -> None:
    dev = ["MC-001 ร้อนผิดปกติ ต้องทำอะไร"]
    holdout = ["mc-001  ร้อนผิดปกติ ต้องทำอะไร?"]  # cosmetic diff only

    report = find_leakage(dev, holdout)

    assert report.leaked
    assert len(report.exact) == 1
    assert report.near == []


def test_find_leakage_detects_near_duplicate() -> None:
    dev = ["เครื่อง MC-001 มีอาการร้อนผิดปกติ ต้องตรวจสอบอะไรบ้าง"]
    holdout = ["เครื่อง MC-001 มีอาการร้อนผิดปกติ ควรตรวจสอบอะไรบ้าง"]  # 1-word paraphrase

    report = find_leakage(dev, holdout, near_dup_threshold=0.5)

    assert report.leaked
    assert len(report.near) == 1
    assert report.near[0].similarity >= 0.5


def test_find_leakage_clean_for_distinct_questions() -> None:
    dev = ["MC-001 ใช้ bearing รุ่นอะไร"]
    holdout = ["ไตรมาสนี้เครื่องไหน downtime มากสุด"]

    report = find_leakage(dev, holdout)

    assert not report.leaked
    assert report.total == 0


def test_jaccard_and_shingles_basic() -> None:
    assert jaccard(char_shingles("abcdef"), char_shingles("abcdef")) == 1.0
    assert jaccard(char_shingles("abcdef"), char_shingles("zzzzzz")) == 0.0


def test_extract_questions_includes_chain_turns() -> None:
    config = {
        "cases": [
            {"id": "a", "question": "Q1"},
            {"id": "b", "turns": [{"question": "Q2"}, {"question": "Q3"}]},
            {"id": "c"},  # no question
        ]
    }
    assert extract_questions(config) == ["Q1", "Q2", "Q3"]
