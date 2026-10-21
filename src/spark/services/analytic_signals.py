"""Analytic-question detection for external Text-to-SQL routing.

Kept out of the (deliberately RAG-only) intent_classifier: these signals decide
whether a question is aggregate/temporal analytics that should hit an external
data source, not what document intent it is. Used by external_sql_routing only
when a factory actually has an enabled external data source configured.
"""

from __future__ import annotations

import re

ANALYTIC_KEYWORDS = [
    "กี่",
    "จำนวน",
    "อันดับ",
    "top",
    "นับ",
    "เฉลี่ย",
    "รวม",
    "ผลรวม",
    "มากที่สุด",
    "สูงสุด",
    "ต่ำสุด",
    "น้อยที่สุด",
    "มากสุด",
    "downtime",
    "total",
    "sum",
    "average",
    "ค่าใช้จ่ายรวม",
    "ค่าใช้จ่าย",
    "เดือนนี้",
    "เดือนที่แล้ว",
    "ไตรมาส",
    "ปีนี้",
    "ปีที่แล้ว",
    "ปีก่อน",
    "this month",
    "last month",
    "this quarter",
    "last quarter",
    "this year",
    "last year",
    "เทียบ",
    "เปรียบเทียบ",
    "พ.ศ",
    "พศ",
]

# These words only indicate SQL when paired with a TEMPORAL or SQL_DOMAIN keyword.
# "เท่าไหร่" alone is also how a spec-lookup question is phrased in Thai
# ("น้ำหนักของ X เท่าไหร่" — a manual/RAG question), so it must be corroborated.
_WEAK_ANALYTIC_KEYWORDS = ["สรุป", "รายงาน", "เดือน", "quarter", "year", "เท่าไหร่"]

AGGREGATE_OVERRIDE_KEYWORDS = [
    "กี่",
    "จำนวน",
    "นับ",
    "รวม",
    "ผลรวม",
    "อันดับ",
    "top",
    "เฉลี่ย",
    "มากที่สุด",
    "สูงสุด",
    "ต่ำสุด",
    "น้อยที่สุด",
    "มากสุด",
    "downtime",
    "total",
    "sum",
    "average",
    "ซ่อมกี่",
    "กี่ครั้ง",
    "กี่ชม",
    "กี่ชั่วโมง",
]

TEMPORAL_ANALYTIC_RE = re.compile(
    r"ปี\s*\d{4}|พ\.?\s*ศ\.?\s*\d{4}|\b2[4-6]\d{2}\b|"
    r"เดือนนี้|เดือนที่แล้ว|เดือนก่อน|ไตรมาสนี้|ไตรมาสที่แล้ว|"
    r"ปีนี้|ปีที่แล้ว|ปีก่อน|this month|last month|this quarter|"
    r"last quarter|this year|last year|"
    r"วันนี้|เมื่อวาน|เมื่อวานนี้|today|yesterday|"
    r"อาทิตย์นี้|อาทิตย์ที่แล้ว|สัปดาห์นี้|สัปดาห์ที่แล้ว|"
    r"this week|last week|"
    r"\d+\s*(?:วัน|เดือน|ปี)(?:\s*(?:ที่ผ่านมา|ล่าสุด|ก่อนหน้า))?|"
    r"\d+\s*(?:day|days|month|months|year|years)",
    flags=re.I,
)

SQL_DOMAIN_KEYWORDS = [
    "ซ่อม",
    "repair",
    "downtime",
    "ค่าใช้จ่าย",
    "cost",
    "เครื่อง",
    "machine",
    "work order",
    "incident",
    "inspection",
    "อะไหล่",
    "stock",
    "purchase",
    "สต๊อก",
    "สต็อก",
    "คงเหลือ",
    "สั่งซื้อ",
    "reorder",
    "ขาดสต๊อก",
    "ขาดสต็อก",
    "po ",
    "spare",
]


def has_analytic_signal(question_lower: str) -> bool:
    if any(k in question_lower for k in ANALYTIC_KEYWORDS):
        return True
    has_weak = any(k in question_lower for k in _WEAK_ANALYTIC_KEYWORDS)
    if has_weak:
        has_domain = any(k in question_lower for k in SQL_DOMAIN_KEYWORDS)
        has_temporal = bool(TEMPORAL_ANALYTIC_RE.search(question_lower))
        if has_domain or has_temporal:
            return True
    return bool(
        TEMPORAL_ANALYTIC_RE.search(question_lower)
        and any(k in question_lower for k in SQL_DOMAIN_KEYWORDS)
    )


def has_aggregate_signal(question_lower: str) -> bool:
    if any(k in question_lower for k in AGGREGATE_OVERRIDE_KEYWORDS):
        return True
    return bool(
        TEMPORAL_ANALYTIC_RE.search(question_lower)
        and any(k in question_lower for k in SQL_DOMAIN_KEYWORDS)
    )
