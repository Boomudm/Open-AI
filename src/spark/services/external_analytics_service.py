"""Text-to-SQL against admin-configured external Postgres sources."""

from __future__ import annotations

import asyncio
import json
import re
import time
from typing import Any

from langchain.prompts import ChatPromptTemplate

from spark.core.config import settings
from spark.core.lazy_singleton import lazy_singleton
from spark.core.llm_client import get_chat_llm
from spark.core.logging import get_logger
from spark.db.models.data_sources import ExternalDataSource
from spark.services.data_source_service import build_schema_context
from spark.services.external_sql.connection import connection_config_from_model, execute_external_select
from spark.services.external_sql.constants import (
    NO_DATA_ANSWER,
    REASON_EMPTY_RESULT,
    REASON_OK,
    REASON_SQL_EXECUTION,
    REASON_SQL_RETRIES_EXHAUSTED,
    REASON_SQL_VALIDATION,
    UNAVAILABLE_ANSWER,
)
from spark.services.external_sql.validator import limit_sql, validate_select_sql

log = get_logger(__name__)

MAX_SQL_RETRIES = 3
MAX_ROWS_FOR_SUMMARY = 50

GENERATE_SQL_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "คุณคือผู้ช่วยสร้าง SQL สำหรับ PostgreSQL ภายนอก\n"
            "ใช้เฉพาะตารางที่ระบุใน schema\n"
            "ตอบเป็น SQL อย่างเดียว ไม่มี markdown",
        ),
        ("human", "{schema}\n\nคำถาม: {question}\n\nสร้าง SQL SELECT"),
    ]
)

FIX_SQL_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "แก้ SQL PostgreSQL ให้ถูกต้อง ตอบเป็น SQL อย่างเดียว",
        ),
        (
            "human",
            "{schema}\n\nคำถาม: {question}\nSQL เดิม:\n{sql}\n\nError:\n{error}\n\nแก้ให้ถูกต้อง",
        ),
    ]
)

SUMMARIZE_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "สรุปผล SQL เป็นภาษาไทย กระชับ ถ้าไม่มีข้อมูลบอกว่าไม่พบข้อมูลที่ตรงเงื่อนไข",
        ),
        ("human", "คำถาม: {question}\nSQL: {sql}\n\nผลลัพธ์ JSON:\n{rows_json}\n\nสรุปคำตอบ"),
    ]
)


def _extract_sql(content: str) -> str:
    text = content.strip()
    fenced = re.search(r"```(?:sql)?\s*(.*?)```", text, flags=re.I | re.S)
    if fenced:
        text = fenced.group(1).strip()
    text = re.sub(r"^\s*(sql|query)\s*:\s*", "", text, flags=re.I)
    return text.strip().rstrip(";")


class ExternalAnalyticsService:
    def _get_llm(self):
        return get_chat_llm(settings.llm_profile)

    async def query(
        self,
        question: str,
        source: ExternalDataSource,
        *,
        factory_id: str | None = None,
        tables: list | None = None,
    ) -> dict[str, Any]:
        start = time.perf_counter()
        # tables is the caller's pre-filtered subset (factory + job-position scoped);
        # falls back to all allowed tables only when a caller doesn't filter.
        visible = tables if tables is not None else source.allowed_tables
        if not visible:
            return self._fail("no allowed tables configured", REASON_SQL_VALIDATION, start)

        allowed = {t.table_name for t in visible}
        schema = build_schema_context(source, visible)
        scope_col = source.scope_column
        scope_val = factory_id if source.factory_id is None else source.factory_id

        sql = ""
        error = ""
        rows: list[dict[str, Any]] = []
        attempts = 0

        while attempts <= MAX_SQL_RETRIES:
            try:
                if attempts == 0 or not sql:
                    chain = GENERATE_SQL_PROMPT | self._get_llm()
                    resp = await asyncio.wait_for(
                        chain.ainvoke({"schema": schema, "question": question}),
                        timeout=settings.sql_llm_timeout_sec,
                    )
                    sql = _extract_sql(resp.content if hasattr(resp, "content") else str(resp))
                else:
                    chain = FIX_SQL_PROMPT | self._get_llm()
                    resp = await asyncio.wait_for(
                        chain.ainvoke(
                            {
                                "schema": schema,
                                "question": question,
                                "sql": sql,
                                "error": error,
                            }
                        ),
                        timeout=settings.sql_llm_timeout_sec,
                    )
                    sql = _extract_sql(resp.content if hasattr(resp, "content") else str(resp))

                ok, reason = validate_select_sql(
                    sql,
                    allowed_tables=allowed,
                    scope_column=scope_col,
                    scope_value=scope_val,
                )
                if not ok:
                    error = reason
                    attempts += 1
                    continue

                exec_sql = limit_sql(sql, settings.external_sql_max_rows)
                cfg = connection_config_from_model(source)
                rows = await execute_external_select(cfg, exec_sql)
                error = ""
                break
            except Exception as exc:
                error = str(exc)[:500]
                attempts += 1

        if error and not rows:
            reason = REASON_SQL_RETRIES_EXHAUSTED if attempts > MAX_SQL_RETRIES else REASON_SQL_EXECUTION
            return self._fail(error, reason, start, sql=sql)

        if not rows:
            return {
                "answer": NO_DATA_ANSWER,
                "sql": sql,
                "rows": [],
                "row_count": 0,
                "reason_code": REASON_EMPTY_RESULT,
                "sql_generation_path": "external_llm_sql",
                "pipeline": "external_sql",
                "data_source_id": str(source.source_id),
                "data_source_name": source.name,
            }

        answer = await self._summarize(question, sql, rows)
        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        log.info(
            "external_analytics_answer",
            source_id=str(source.source_id),
            row_count=len(rows),
            latency_ms=latency_ms,
        )
        return {
            "answer": answer,
            "sql": sql,
            "rows": rows[:MAX_ROWS_FOR_SUMMARY],
            "row_count": len(rows),
            "reason_code": REASON_OK,
            "sql_generation_path": "external_llm_sql",
            "pipeline": "external_sql",
            "data_source_id": str(source.source_id),
            "data_source_name": source.name,
        }

    async def _summarize(self, question: str, sql: str, rows: list[dict[str, Any]]) -> str:
        try:
            chain = SUMMARIZE_PROMPT | self._get_llm()
            resp = await asyncio.wait_for(
                chain.ainvoke(
                    {
                        "question": question,
                        "sql": sql,
                        "rows_json": json.dumps(rows[:MAX_ROWS_FOR_SUMMARY], ensure_ascii=False, default=str),
                    }
                ),
                timeout=settings.sql_llm_timeout_sec,
            )
            return (resp.content if hasattr(resp, "content") else str(resp)).strip()
        except Exception:
            return UNAVAILABLE_ANSWER

    def _fail(
        self,
        detail: str,
        reason_code: str,
        started_at: float,
        *,
        sql: str = "",
    ) -> dict[str, Any]:
        log.warning("external_analytics_failed", detail=detail[:200], reason_code=reason_code)
        return {
            "answer": NO_DATA_ANSWER,
            "sql": sql,
            "rows": [],
            "row_count": 0,
            "reason_code": reason_code,
            "sql_generation_path": "external_llm_sql",
            "pipeline": "external_sql",
            "error_detail": detail[:200],
            "latency_ms": round((time.perf_counter() - started_at) * 1000, 2),
        }


external_analytics_service = lazy_singleton(lambda: ExternalAnalyticsService())
