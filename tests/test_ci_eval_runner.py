"""CI eval runner: expect: block schema (sources / contains / no_data / answer_path)."""

from __future__ import annotations

from spark.eval.ci_eval_runner import (
    _check_case_expectations,
    _ragfilter_kwargs,
    _source_matches,
)


def test_source_matches_document_type_and_file() -> None:
    sources = [{"document_type": "io_mapping", "source_file": "MAPPING.xlsx", "page": None}]
    assert _source_matches({"document_type": "io_mapping", "source_file_contains": "mapping"}, sources)
    assert not _source_matches({"document_type": "machine_manual"}, sources)


def test_source_matches_page() -> None:
    sources = [{"document_type": "drawing", "source_file": "wiring_diagram.pdf", "page": 7}]
    assert _source_matches({"document_type": "drawing", "page": 7}, sources)
    assert not _source_matches({"document_type": "drawing", "page": 1}, sources)


def test_check_case_expectations_no_data_pass() -> None:
    issues = _check_case_expectations(
        {"no_data": True, "max_sources": 0},
        answer="ไม่พบข้อมูลในระบบ กรุณาติดต่อวิศวกร",
        answer_path="query_policy_block",
        sources=[],
    )
    assert issues == []


def test_check_case_expectations_no_data_fail_when_answered() -> None:
    issues = _check_case_expectations(
        {"no_data": True},
        answer="RES0.BELT_CALIB_SENSOR connects to EcoRT_0",
        answer_path="grounded_llm",
        sources=[{"document_type": "io_mapping"}],
    )
    assert any("no_data" in i for i in issues)


def test_check_case_expectations_answer_contains_any() -> None:
    issues = _check_case_expectations(
        {"answer_contains_any": ["EcoRT_0", "BOOL"]},
        answer="ต่อกับ EcoRT_0 ที่ RES0.BELT_CALIB_SENSOR",
        answer_path="grounded_llm",
        sources=[],
    )
    assert issues == []

    issues = _check_case_expectations(
        {"answer_contains_any": ["not-present-token"]},
        answer="ต่อกับ EcoRT_0",
        answer_path="grounded_llm",
        sources=[],
    )
    assert issues


def test_check_case_expectations_forbidden_contains_catches_corruption() -> None:
    issues = _check_case_expectations(
        {"answer_forbidden_contains": ["WATEERc_oERNTA"]},
        answer="RES0.FB_MANUAL_CONTROL_WATEERc_oERNTA_20 is a corrupted tag",
        answer_path="grounded_llm",
        sources=[],
    )
    assert issues


def test_check_case_expectations_sources_spec() -> None:
    sources = [{"document_type": "io_mapping", "source_file": "MAPPING.xlsx"}]
    issues = _check_case_expectations(
        {"sources": [{"document_type": "io_mapping", "source_file_contains": "MAPPING"}]},
        answer="...",
        answer_path="grounded_llm",
        sources=sources,
    )
    assert issues == []

    issues = _check_case_expectations(
        {"sources": [{"document_type": "machine_manual"}]},
        answer="...",
        answer_path="grounded_llm",
        sources=sources,
    )
    assert issues


def test_ragfilter_kwargs_from_filter_block() -> None:
    case = {"filter": {"factory_id": "F-01", "machine_id": "MC-002", "only_active": False, "bogus_field": "x"}}
    kwargs = _ragfilter_kwargs(case)
    assert kwargs == {"factory_id": "F-01", "machine_id": "MC-002", "only_active": False}


def test_ragfilter_kwargs_legacy_factory_id() -> None:
    assert _ragfilter_kwargs({"factory_id": "F-01"}) == {"factory_id": "F-01"}
    assert _ragfilter_kwargs({}) == {}
