"""PLC-tag detection gates both the io_mapping intent (which applies a STRICT
document_type filter) and the exact-match lookup — file names and web hosts in
a query must never count as tags, or ordinary questions about a named PDF get
locked out of the very document they name."""

from __future__ import annotations

import pytest

from spark.retrieval.intent.router import IntentRouter, QueryIntent
from spark.retrieval.lexical.tokenize_industrial import extract_plc_tags, has_plc_tag


@pytest.mark.parametrize(
    "query,expected",
    [
        ("RES0.BELT_CALIB_SENSOR เชื่อมกับอะไร", ["RES0.BELT_CALIB_SENSOR"]),
        ("RES0.SERVO_BELT.Destination คืออะไร", ["RES0.SERVO_BELT.Destination"]),
        ("RES0.MODBUSRREG8_Operation_Control_3_10.r2LinkName", ["RES0.MODBUSRREG8_Operation_Control_3_10.r2LinkName"]),
    ],
)
def test_real_tags_extracted(query: str, expected: list[str]) -> None:
    assert extract_plc_tags(query) == expected


@pytest.mark.parametrize(
    "query",
    [
        "อธิบายหน้า 5 ของ KSS_Manual.pdf",
        "ดูไฟล์ MAPPING.xlsx ให้หน่อย",
        "เว็บ thaimectech.com คือของบริษัทไหน",
        "เปิด wiring diagram.pdf หน้าไหนมี EE-07",
        "config อยู่ใน settings.yaml",
    ],
)
def test_filenames_and_hosts_are_not_tags(query: str) -> None:
    assert extract_plc_tags(query) == []
    assert not has_plc_tag(query)


def test_filename_query_does_not_route_to_io_mapping_intent() -> None:
    plan = IntentRouter().route("อธิบายหน้า 5 ของ KSS_Manual.pdf")
    assert plan.intent != QueryIntent.IO_MAPPING


def test_duplicate_tags_deduplicated_order_preserved() -> None:
    tags = extract_plc_tags("RES0.B_2 กับ RES0.A_1 และ RES0.B_2 อีกครั้ง")
    assert tags == ["RES0.B_2", "RES0.A_1"]
