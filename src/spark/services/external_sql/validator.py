"""Shared SQL safety checks for external Text-to-SQL."""

from __future__ import annotations

import re

FORBIDDEN_SQL_KEYWORDS = {
    "insert",
    "update",
    "delete",
    "drop",
    "alter",
    "create",
    "truncate",
    "grant",
    "revoke",
    "merge",
    "call",
    "execute",
    "exec",
    "set_config",
    "current_setting",
    "pg_sleep",
}


def extract_table_refs(sql: str) -> set[str]:
    refs: set[str] = set()
    for match in re.finditer(r"\b(?:from|join)\s+([a-zA-Z_][\w.]*)", sql, flags=re.I):
        token = match.group(1).split(".")[-1].strip('"`[]').casefold()
        refs.add(token)
    return refs


def validate_select_sql(
    sql: str,
    *,
    allowed_tables: set[str],
    scope_column: str | None = None,
    scope_value: str | None = None,
) -> tuple[bool, str]:
    stripped = sql.strip().rstrip(";")
    low = stripped.casefold()
    if not stripped:
        return False, "SQL ว่าง"
    if not (low.startswith("select") or low.startswith("with")):
        return False, "อนุญาตเฉพาะ SELECT"
    if ";" in stripped:
        return False, "ห้ามส่งหลาย statement"
    for kw in FORBIDDEN_SQL_KEYWORDS:
        if re.search(rf"\b{re.escape(kw)}\b", low):
            return False, f"พบคำสั่งที่ไม่อนุญาต: {kw}"

    allowed_folded = {t.casefold() for t in allowed_tables}
    refs = extract_table_refs(stripped)
    if refs and not refs.issubset(allowed_folded):
        invalid = sorted(refs.difference(allowed_folded))
        return False, f"อ้างอิงตารางที่ไม่อนุญาต: {', '.join(invalid)}"
    if not refs.intersection(allowed_folded):
        return False, "ต้องอ้างอิงตารางที่อนุญาตอย่างน้อย 1 ตาราง"

    if scope_column and scope_value:
        col = scope_column.casefold()
        if col not in low:
            return False, f"SQL ต้องจำกัดขอบเขตด้วย {scope_column}"
        norm_val = re.sub(r"[^A-Z0-9]", "", scope_value.upper())
        norm_sql = re.sub(r"[^A-Z0-9]", "", stripped.upper())
        if norm_val and norm_val not in norm_sql:
            return False, f"SQL ต้อง filter {scope_column} = {scope_value!r}"

    return True, ""


def limit_sql(sql: str, max_rows: int) -> str:
    stripped = sql.strip().rstrip(";")
    if re.search(r"\blimit\s+\d+\b", stripped, flags=re.I):
        return stripped
    return f"SELECT * FROM ({stripped}) AS spark_limited LIMIT {max_rows}"
