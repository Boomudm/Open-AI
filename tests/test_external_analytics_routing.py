"""External Text-to-SQL analytics: signal detection, validation, routing, engine.

All external-DB and LLM calls are mocked, so these run without Postgres or a
live external source.
"""

from __future__ import annotations

import uuid

import pytest
from langchain_core.runnables import RunnableLambda

from spark.core.secret_box import decrypt_secret, encrypt_secret
from spark.db.models.data_sources import ExternalDataSource, ExternalDataSourceTable
from spark.services.analytic_signals import has_aggregate_signal, has_analytic_signal
from spark.services.data_source_service import ExternalSourceBundle
from spark.services.external_analytics_service import ExternalAnalyticsService
from spark.services.external_sql.constants import REASON_OK, REASON_SQL_RETRIES_EXHAUSTED
from spark.services.external_sql.validator import validate_select_sql
from spark.services.external_sql_routing import try_external_analytics
from spark.services.intent_classifier import QuestionRouting


# --- 1. analytic-signal detection: count/trend => SQL, spec/how-to => RAG ----


@pytest.mark.parametrize(
    "question",
    [
        "เครื่อง MC-001 ซ่อมกี่ครั้งเดือนนี้",
        "downtime รวมของโรงงานปีนี้เท่าไหร่",
        "เครื่องไหนซ่อมบ่อยสุด 5 อันดับแรก",
        "ค่าใช้จ่ายซ่อมเดือนที่แล้วรวมเท่าไหร่",
        "จำนวน work order ที่ค้างอยู่",
        "เทียบ downtime ปีนี้กับปีที่แล้ว",
    ],
)
def test_analytic_questions_signal_true(question: str) -> None:
    q = question.casefold()
    assert has_analytic_signal(q) or has_aggregate_signal(q)


@pytest.mark.parametrize(
    "question",
    [
        "แรงดันไฟฟ้าของ MC-001 เท่าไหร่",
        "วิธี reset alarm เครื่อง KUKA",
        "ขั้นตอนเปลี่ยนน้ำมันเครื่อง",
        "สวัสดีครับ",
    ],
)
def test_document_questions_signal_false(question: str) -> None:
    q = question.casefold()
    assert not (has_analytic_signal(q) or has_aggregate_signal(q))


# --- 2. SQL validator safety ------------------------------------------------


def test_validator_allows_scoped_select() -> None:
    ok, _ = validate_select_sql(
        "SELECT count(*) FROM work_orders WHERE factory_id='F-01'",
        allowed_tables={"work_orders"},
        scope_column="factory_id",
        scope_value="F-01",
    )
    assert ok is True


def test_validator_blocks_writes_and_unknown_tables() -> None:
    bad_drop, _ = validate_select_sql("DROP TABLE work_orders", allowed_tables={"work_orders"})
    assert bad_drop is False
    bad_tbl, _ = validate_select_sql(
        "SELECT * FROM secret_payroll", allowed_tables={"work_orders"}
    )
    assert bad_tbl is False


def test_validator_requires_scope_filter() -> None:
    ok, reason = validate_select_sql(
        "SELECT count(*) FROM work_orders",
        allowed_tables={"work_orders"},
        scope_column="factory_id",
        scope_value="F-01",
    )
    assert ok is False
    assert "factory_id" in reason


def test_secret_box_round_trip() -> None:
    assert decrypt_secret(encrypt_secret("p@ss-รหัส")) == "p@ss-รหัส"


# --- 3. try_external_analytics routing gate ---------------------------------


def _bundle() -> ExternalSourceBundle:
    src = _source()
    tbl = _table(src)
    return ExternalSourceBundle(
        source=src, allowed_table_names=frozenset({"work_orders"}), visible_tables=[tbl]
    )


def _source() -> ExternalDataSource:
    return ExternalDataSource(
        source_id=uuid.uuid4(),
        name="cmms",
        host="db.internal",
        port=5432,
        database_name="cmms",
        username="ro",
        password_encrypted=encrypt_secret("pw"),
        ssl_mode="prefer",
        scope_column="factory_id",
        factory_id=None,
        is_enabled=True,
    )


def _table(src: ExternalDataSource) -> ExternalDataSourceTable:
    return ExternalDataSourceTable(
        table_id=uuid.uuid4(),
        source_id=src.source_id,
        schema_name="public",
        table_name="work_orders",
        description="ประวัติงานซ่อม",
        columns_meta=[
            {"column_name": "factory_id", "data_type": "text"},
            {"column_name": "machine_id", "data_type": "text"},
            {"column_name": "created_at", "data_type": "timestamp"},
        ],
    )


_RAG_ROUTING = QuestionRouting(route="rag", is_followup=False, reason="default:factual")


@pytest.mark.asyncio
async def test_routing_none_without_factory() -> None:
    result = await try_external_analytics(
        None, "ซ่อมกี่ครั้ง", _RAG_ROUTING, factory_id=None
    )
    assert result is None


@pytest.mark.asyncio
async def test_routing_none_without_source(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _resolve(*a, **k):
        return None

    monkeypatch.setattr(
        "spark.services.data_source_service.resolve_external_source_for_factory", _resolve
    )
    result = await try_external_analytics(
        None, "เครื่อง MC-001 ซ่อมกี่ครั้งเดือนนี้", _RAG_ROUTING, factory_id="F-01"
    )
    assert result is None


class _FakeService:
    """Stand-in for the lazy_singleton external_analytics_service."""

    def __init__(self, result: dict) -> None:
        self.result = result
        self.calls = 0

    async def query(self, question, source, *, factory_id=None, tables=None):
        self.calls += 1
        return self.result


@pytest.mark.asyncio
async def test_routing_none_for_non_analytic_question(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _resolve(*a, **k):
        return _bundle()

    fake = _FakeService({"answer": "x"})
    monkeypatch.setattr(
        "spark.services.data_source_service.resolve_external_source_for_factory", _resolve
    )
    monkeypatch.setattr(
        "spark.services.external_analytics_service.external_analytics_service", fake
    )
    # A pure how-to question must NOT be sent to SQL even when a source exists.
    result = await try_external_analytics(
        None, "วิธีเปลี่ยนน้ำมันเครื่อง", _RAG_ROUTING, factory_id="F-01"
    )
    assert result is None
    assert fake.calls == 0


@pytest.mark.asyncio
async def test_routing_runs_sql_for_analytic_question(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _resolve(*a, **k):
        return _bundle()

    fake = _FakeService(
        {"answer": "เดือนนี้ซ่อม 3 ครั้ง", "reason_code": REASON_OK, "pipeline": "external_sql"}
    )
    monkeypatch.setattr(
        "spark.services.data_source_service.resolve_external_source_for_factory", _resolve
    )
    monkeypatch.setattr(
        "spark.services.external_analytics_service.external_analytics_service", fake
    )
    result = await try_external_analytics(
        None, "เครื่อง MC-001 ซ่อมกี่ครั้งเดือนนี้", _RAG_ROUTING, factory_id="F-01"
    )
    assert result is not None
    assert fake.calls == 1
    assert result["pipeline"] == "external_sql"
    assert result["reason_code"] == REASON_OK


# --- 4. ExternalAnalyticsService engine (mocked LLM + external DB) -----------


class _Resp:
    def __init__(self, content: str) -> None:
        self.content = content


def _fake_llm(sql: str, summary: str) -> RunnableLambda:
    def _run(prompt_value):
        text = prompt_value.to_string() if hasattr(prompt_value, "to_string") else str(prompt_value)
        return _Resp(summary if "สรุปคำตอบ" in text else sql)

    return RunnableLambda(_run)


@pytest.mark.asyncio
async def test_engine_generates_validates_executes_summarizes(monkeypatch: pytest.MonkeyPatch) -> None:
    src = _source()
    tbl = _table(src)
    svc = ExternalAnalyticsService()

    good_sql = "SELECT count(*) AS n FROM work_orders WHERE factory_id='F-01'"
    monkeypatch.setattr(
        ExternalAnalyticsService,
        "_get_llm",
        lambda self: _fake_llm(good_sql, "เดือนนี้ซ่อม 3 ครั้งครับ"),
    )

    async def _fake_exec(cfg, sql, *, timeout_ms=None):
        assert "work_orders" in sql
        return [{"n": 3}]

    monkeypatch.setattr(
        "spark.services.external_analytics_service.execute_external_select", _fake_exec
    )

    out = await svc.query(
        "เครื่อง MC-001 ซ่อมกี่ครั้งเดือนนี้", src, factory_id="F-01", tables=[tbl]
    )
    assert out["reason_code"] == REASON_OK
    assert out["row_count"] == 1
    assert out["answer"] == "เดือนนี้ซ่อม 3 ครั้งครับ"
    assert out["pipeline"] == "external_sql"
    assert "factory_id" in out["sql"].lower()


@pytest.mark.asyncio
async def test_engine_rejects_unsafe_sql_and_exhausts_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    src = _source()
    tbl = _table(src)
    svc = ExternalAnalyticsService()

    # LLM keeps producing a forbidden write — validator must block every attempt.
    monkeypatch.setattr(
        ExternalAnalyticsService,
        "_get_llm",
        lambda self: _fake_llm("DROP TABLE work_orders", "should-not-run"),
    )

    async def _fake_exec(cfg, sql, *, timeout_ms=None):  # pragma: no cover - must not run
        raise AssertionError("unsafe SQL reached execution")

    monkeypatch.setattr(
        "spark.services.external_analytics_service.execute_external_select", _fake_exec
    )

    out = await svc.query("ลบตาราง", src, factory_id="F-01", tables=[tbl])
    assert out["reason_code"] == REASON_SQL_RETRIES_EXHAUSTED
    assert out["row_count"] == 0


# --- 5. compound questions: per-part SQL + residual document part ------------


class _RecordingService:
    """Fake engine that records each part-question it is asked."""

    def __init__(self) -> None:
        self.questions: list[str] = []

    async def query(self, question, source, *, factory_id=None, tables=None):
        self.questions.append(question)
        return {
            "answer": f"คำตอบของ: {question}",
            "sql": f"SELECT 1 -- {question[:20]}",
            "rows": [{"n": 1}],
            "row_count": 1,
            "reason_code": REASON_OK,
            "sql_generation_path": "external_llm_sql",
            "pipeline": "external_sql",
            "data_source_id": "sid",
            "data_source_name": "cmms",
        }


def _patch_bundle(monkeypatch: pytest.MonkeyPatch, service) -> None:
    async def _resolve(*a, **k):
        return _bundle()

    monkeypatch.setattr(
        "spark.services.data_source_service.resolve_external_source_for_factory", _resolve
    )
    monkeypatch.setattr(
        "spark.services.external_analytics_service.external_analytics_service", service
    )


@pytest.mark.asyncio
async def test_mixed_compound_returns_sql_sections_and_residual(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    svc = _RecordingService()
    _patch_bundle(monkeypatch, svc)
    result = await try_external_analytics(
        None,
        "เดือนนี้ MC-777 ซ่อมกี่ครั้ง และ safe input ของ KUKA สถานะ ON คือช่วงแรงดันเท่าไหร่",
        _RAG_ROUTING,
        factory_id="F-01",
    )
    assert result is not None
    # Only the analytic part hit SQL — with its month filter intact.
    assert svc.questions == ["เดือนนี้ MC-777 ซ่อมกี่ครั้ง"]
    assert len(result["sql_sections"]) == 1
    # The document part comes back for the RAG pipelines — clean, without the
    # SQL-side identifier carry-over pinned onto it.
    assert "safe input" in result["residual_question"]
    assert "MC-777" not in result["residual_question"]


@pytest.mark.asyncio
async def test_all_analytic_compound_runs_sql_per_part_with_identifier_carry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    svc = _RecordingService()
    _patch_bundle(monkeypatch, svc)
    result = await try_external_analytics(
        None,
        "MC-777 เดือนนี้ซ่อมกี่ครั้ง และค่าใช้จ่ายรวมเท่าไหร่",
        _RAG_ROUTING,
        factory_id="F-01",
    )
    assert result is not None
    assert result.get("residual_question") is None
    assert len(svc.questions) == 2
    # Part 2 lost both its machine id and its time window in the split — both
    # must be carried over or the SQL aggregates factory-wide and all-time.
    assert "MC-777" in svc.questions[1]
    assert "เดือนนี้" in svc.questions[1]
    # Combined answer renders both sections.
    assert "1)" in result["answer"] and "2)" in result["answer"]


@pytest.mark.asyncio
async def test_doc_only_compound_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    svc = _RecordingService()
    _patch_bundle(monkeypatch, svc)
    result = await try_external_analytics(
        None,
        "spec แรงดันของ safe input คือเท่าไหร่ และ สายไฟ CN7 ต้องใช้ขนาดเบอร์อะไร",
        _RAG_ROUTING,
        factory_id="F-01",
    )
    assert result is None
    assert svc.questions == []


def test_merge_compound_answer_renders_sections_then_rag() -> None:
    from spark.services.external_sql_routing import merge_compound_answer

    external = {
        "sql_sections": [
            {"question": "ซ่อมกี่ครั้ง", "answer": "4 ครั้ง"},
        ],
        "residual_question": "แรงดัน safe input เท่าไหร่",
    }
    merged = merge_compound_answer(external, "ช่วง 11-30 V ครับ")
    assert merged.index("4 ครั้ง") < merged.index("11-30 V")
    assert "**1) ซ่อมกี่ครั้ง**" in merged
    assert "**2) แรงดัน safe input เท่าไหร่**" in merged
