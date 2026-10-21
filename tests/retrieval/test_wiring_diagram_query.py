"""Query-side wiring-diagram understanding: tokens, routing, exact terms.

A field technician asks about a wiring diagram by device tag ("K1 คุมอะไร"),
terminal ("X1:5 ไปไหน"), or rail ("24VDC มาจากไหน") — never by the word
"diagram". These tests pin the query-side plumbing that turns that phrasing
into retrieval signal: industrial tokens (exact leg + boost_tokens + evidence
scoring), the soft drawing route, and terminal-phrase normalization.
"""

from __future__ import annotations

import pytest

from spark.retrieval.intent import features
from spark.retrieval.intent.glossary import expand_lexical_variants
from spark.retrieval.intent.router import IntentRouter
from spark.retrieval.intent.types import QueryIntent
from spark.retrieval.lexical.tokenize_industrial import extract_industrial_tokens


# --- industrial tokens ------------------------------------------------------


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("K1 คุมอะไร", "K1"),
        ("CB1 ตัดไฟส่วนไหน", "CB1"),
        ("MCB2 คุมโซนไหน", "MCB2"),
        ("relay R3 ทำหน้าที่อะไร", "R3"),
        ("F2 ขาดจะเกิดอะไรขึ้น", "F2"),
        ("แหล่งจ่ายไฟ 24VDC มาจากไหน", "24VDC"),
        ("PE ต่อที่จุดไหนบ้าง", "PE"),
        ("ไฟ L1 หายทั้งเฟส", "L1"),
        ("AZD-KEP รับไฟจากไหน", "AZD-KEP"),
        ("SPD-CTRL ทำงานยังไง", "SPD-CTRL"),
        # QM (motor-protection breaker), SV (solenoid valve), VSD (drive) are
        # the dominant families on the F-05 MAIN-cabinet drawing — a QM1/SV4
        # question that extracts no tokens never reaches the device index.
        ("ถ้าเบรกเกอร์ QM1 ในตู้ MAIN trip ไฟจะดับที่อุปกรณ์ไหนบ้าง", "QM1"),
        ("โซลินอยด์ SV4 ต่อกับอะไร", "SV4"),
        ("VSD1 รับไฟจากเฟสไหน", "VSD1"),
    ],
)
def test_electrical_tags_extracted(query: str, expected: str) -> None:
    assert expected in extract_industrial_tokens(query)


def test_hyphenated_machine_id_is_not_an_iec_tag() -> None:
    # "SV-01" is a machine id, not a solenoid tag — the digit must follow the
    # prefix directly, so hyphenated ids stay with the machine-id extractor.
    from spark.retrieval.lexical.tokenize_industrial import _IEC_DEVICE_TAG_RE

    assert _IEC_DEVICE_TAG_RE.search("มอเตอร์ SV-01 ขึ้น alarm") is None


def test_terminal_ref_emits_full_ref_and_device_half() -> None:
    tokens = extract_industrial_tokens("X1:5 ต่อไปที่ไหน")
    assert "X1:5" in tokens
    assert "X1" in tokens


def test_terminal_ref_with_named_terminal() -> None:
    tokens = extract_industrial_tokens("M18:GND ต่อร่วมกับใคร")
    assert "M18:GND" in tokens
    assert "M18" in tokens


def test_lowercase_hyphenated_english_is_not_a_model_code() -> None:
    # _CAPS_HYPHEN_MODEL_RE is case-sensitive on purpose.
    assert "NON-EXCITATION" not in extract_industrial_tokens(
        "non-excitation brake ทำงานอย่างไร"
    )


def test_open_letter_digit_pairs_stay_out_of_tag_set() -> None:
    # "A4" (paper size / figure ref) must not become a device tag — the IEC
    # prefix set is deliberately closed.
    assert "A4" not in extract_industrial_tokens("ดูตาราง A4 หน้า 12")


def test_hex_alarm_codes_survive_alongside_tag_patterns() -> None:
    assert "26H" in extract_industrial_tokens("alarm 26h Motor overheat แก้ยังไง")


# --- wiring-connectivity routing --------------------------------------------


@pytest.mark.parametrize(
    "query",
    [
        "M18 ต่อกับอะไรบ้าง",
        "X1:5 ต่อไปที่ไหน",
        "ถ้า M18 เสีย กระทบอะไรบ้าง",
        "K1 รับไฟจากไหน",
        "ไฟเข้าตู้มาจากเบรกเกอร์ตัวไหน",
        "สายเบอร์ 205 ไปไหน",
        "กราวด์ของ AZD-KEP ต่อที่จุดไหน",
    ],
)
def test_connectivity_questions_detected(query: str) -> None:
    assert features.has_wiring_connectivity_terms(query)


@pytest.mark.parametrize(
    "query",
    [
        # Troubleshooting verbs stay out — the manual often answers better.
        "มอเตอร์ M18 ไม่หมุน เช็คอะไรบ้าง",
        # Connectivity phrasing with no electrical anchor.
        "ต่อไปเราทำอะไรกันดี",
        "งานต่อไปคืออะไร",
        # No connectivity phrasing at all.
        "M18 คืออะไร",
    ],
)
def test_non_connectivity_questions_not_detected(query: str) -> None:
    assert not features.has_wiring_connectivity_terms(query)


def test_router_soft_drawing_route_for_connectivity() -> None:
    plan = IntentRouter().route("M18 ต่อกับอะไรบ้าง")
    assert plan.intent == QueryIntent.DRAWING
    assert plan.route_source == "regex_drawing_connectivity"
    # Soft: a manual may carry the answer — never hard-filter to drawings.
    assert plan.strict_document_type_filter is False
    assert plan.document_type_hint == "drawing"


def test_router_explicit_drawing_stays_strict() -> None:
    plan = IntentRouter().route("ขอดู wiring diagram ของ M18")
    assert plan.intent == QueryIntent.DRAWING
    assert plan.route_source == "regex_drawing"
    assert plan.strict_document_type_filter is True


def test_router_loto_still_wins_over_connectivity() -> None:
    plan = IntentRouter().route("ขั้นตอน lockout ก่อนถอดสาย K1 ต่อกับอะไร")
    assert plan.intent == QueryIntent.SAFETY_LOTO


# --- exact terms & glossary ---------------------------------------------------


def test_terminal_phrase_normalized_to_table_form() -> None:
    from spark.retrieval.exact import exact_evidence_terms

    terms = exact_evidence_terms("X1 ขา 5 ต่อไปที่ไหน")
    assert "X1:5" in terms


def test_terminal_phrase_english_pin_form() -> None:
    from spark.retrieval.exact import exact_evidence_terms

    terms = exact_evidence_terms("CN1 pin 3 ต่อกับอะไร")
    assert "CN1:3" in terms


def test_glossary_bridges_thai_electrical_terms() -> None:
    expanded = expand_lexical_variants("กราวด์ของมอเตอร์ต่อที่ไหน").lower()
    assert "gnd" in expanded
    expanded = expand_lexical_variants("รีเลย์ตัวไหนคุมคอนแทคเตอร์").lower()
    assert "relay" in expanded
    assert "contactor" in expanded


def test_prompt_allows_device_index_page_numbers() -> None:
    from spark.generation.prompts import SYSTEM_PROMPT

    # Rule 11 carve-out: page numbers printed inside the document (device
    # index) are quotable content; rule 12 shapes wiring answers.
    assert "ดัชนีอุปกรณ์" in SYSTEM_PROMPT
    assert "Tag:Terminal" in SYSTEM_PROMPT
