"""Shared answer strings + reason codes for external Text-to-SQL.

These were previously exported by the internal ``analytics_service`` (removed in
the RAG-only simplification). They live here now so the external data-source
path has no dependency on the deleted internal analytics engine.
"""

from __future__ import annotations

# Mirrors the RAG NO_DATA tone so SQL and RAG "not found" replies read alike.
NO_DATA_ANSWER = "ไม่พบข้อมูลในระบบ กรุณาติดต่อวิศวกร"
UNAVAILABLE_ANSWER = "ระบบ AI ไม่พร้อมชั่วคราว กรุณาติดต่อวิศวกร"

REASON_OK = "ok"
REASON_EMPTY_RESULT = "empty_result"
REASON_SQL_VALIDATION = "sql_validation_failed"
REASON_SQL_EXECUTION = "sql_execution_failed"
REASON_SQL_RETRIES_EXHAUSTED = "sql_retries_exhausted"
REASON_SERVICE_FAILED = "service_failed"
