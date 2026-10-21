"""Agentic tool wrapper around analytics_service.query()."""

from __future__ import annotations

import time

from spark.services.agentic.sql_citations import ensure_sql_answer_citations
from spark.services.agentic.types import (
    DatabaseScope,
    QueryDatabaseResult,
    RBACContext,
)
from spark.services.analytics_service import REASON_OK, analytics_service


def _require_scope(scope: DatabaseScope | None) -> DatabaseScope:
    if scope is None:
        raise ValueError("scope is required for query_database")
    if not scope.factory_id and not scope.machine_id:
        raise ValueError("scope must include factory_id or machine_id")
    return scope


def _require_rbac_context(rbac_context: RBACContext | None) -> RBACContext:
    if rbac_context is None:
        raise ValueError("rbac_context is required for query_database")
    return rbac_context


async def query_database(
    question: str,
    scope: DatabaseScope,
    rbac_context: RBACContext,
) -> QueryDatabaseResult:
    """Wrap analytics_service.query() — preserves validation; adds SQL citations."""
    resolved_scope = _require_scope(scope)
    rbac = _require_rbac_context(rbac_context)
    start = time.perf_counter()
    result = await analytics_service.query(
        question,
        factory_id=resolved_scope.factory_id,
        machine_id=resolved_scope.machine_id,
        allowed_factory_ids=rbac.allowed_factory_ids,
    )
    rows = list(result.get("rows") or [])
    sql = str(result.get("sql") or "")
    answer = str(result.get("answer") or "")
    cited_answer, citation_refs = ensure_sql_answer_citations(
        answer,
        sql=sql,
        rows=rows,
    )
    semantic_passed = bool(result.get("semantic_passed")) and result.get("reason_code") == REASON_OK
    return QueryDatabaseResult(
        answer=cited_answer,
        sql_generated=sql,
        rows_returned=int(result.get("row_count") or 0),
        semantic_validation_passed=semantic_passed,
        citation_refs=citation_refs,
        latency_ms=round((time.perf_counter() - start) * 1000, 2),
        rows=rows,
    )
