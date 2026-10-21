"""SQL answer citation helpers — mirror RAG _ensure_answer_citations bracket format."""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

_ID_FIELD_TABLE: tuple[tuple[str, str], ...] = (
    ("work_order_id", "work_orders"),
    ("wo_id", "work_orders"),
    ("repair_id", "repair_history"),
    ("purchase_order_id", "purchase_orders"),
    ("po_id", "purchase_orders"),
    ("part_id", "spare_parts"),
    ("machine_id", "machines"),
)

_DATE_FIELDS: tuple[str, ...] = (
    "repair_date",
    "created_at",
    "updated_at",
    "order_date",
    "event_date",
    "completed_at",
    "started_at",
)


def _infer_table_name(sql: str) -> str:
    if not sql:
        return "query_result"
    match = re.search(r"\bfrom\s+(?:[\w.]+\.)?(\"?\w+\"?)", sql, flags=re.IGNORECASE)
    if not match:
        return "query_result"
    return match.group(1).strip('"')


def _normalize_date(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value).strip()
    if not text:
        return None
    return text[:10]


def _date_range_label(rows: list[dict[str, Any]]) -> str | None:
    collected: list[str] = []
    for row in rows:
        for key in _DATE_FIELDS:
            normalized = _normalize_date(row.get(key))
            if normalized:
                collected.append(normalized)
    if not collected:
        return None
    collected.sort()
    if collected[0] == collected[-1]:
        return collected[0]
    return f"{collected[0]} – {collected[-1]}"


def build_sql_citation_refs(
    *,
    sql: str,
    rows: list[dict[str, Any]],
    max_refs: int = 3,
) -> list[str]:
    """Build bracket citations from SQL result rows."""
    refs: list[str] = []
    seen: set[str] = set()

    def _add(ref: str) -> None:
        if ref in seen or len(refs) >= max_refs:
            return
        seen.add(ref)
        refs.append(ref)

    for row in rows:
        for field, table in _ID_FIELD_TABLE:
            value = row.get(field)
            if value is None or str(value).strip() == "":
                continue
            if field.endswith("_id") and field not in ("work_order_id", "wo_id"):
                _add(f"[{table} row {value}]")
            else:
                _add(f"[{table}, {value}]")

        row_number = row.get("row_number")
        if row_number is not None:
            table = _infer_table_name(sql)
            _add(f"[{table} row {row_number}]")

    if refs:
        return refs

    table = _infer_table_name(sql)
    date_range = _date_range_label(rows)
    if date_range:
        _add(f"[{table} {date_range}]")
    elif table != "query_result":
        _add(f"[{table}]")
    return refs


def ensure_sql_answer_citations(
    answer: str,
    *,
    sql: str,
    rows: list[dict[str, Any]],
) -> tuple[str, list[str]]:
    """Append SQL citations when the summary does not already mention them."""
    from spark.retrieval.constants import NO_DATA_ANSWER, UNAVAILABLE_ANSWER

    if not answer or answer in (NO_DATA_ANSWER, UNAVAILABLE_ANSWER):
        return answer, []
    refs = build_sql_citation_refs(sql=sql, rows=rows)
    if not refs:
        return answer, []
    if any(ref in answer or ref.strip("[]") in answer for ref in refs):
        return answer, refs
    return f"{answer.rstrip()}\n\nอ้างอิง: {', '.join(refs)}", refs
