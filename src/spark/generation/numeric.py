"""Unit-aware numeric grounding — Latin + Thai numerals (Phase 10)."""

from __future__ import annotations

import re
from dataclasses import dataclass

_THAI_DIGIT_MAP = str.maketrans("๐๑๒๓๔๕๖๗๘๙", "0123456789")

_NUMERIC_RE = re.compile(
    r"""
    (?<!\w)
    (?P<raw>
        \d{1,3}(?:,\d{3})+(?:\.\d+)?|
        \d+(?:\.\d+)?
    )
    \s*
    (?P<unit>
        °\s*[cC]|°|℃|
        \s*(?:°\s*)?(?:C|F|K)\b|
        \s*(?:degree|degrees|deg)\b|
        \s*(?:mm|cm|m|km|bar|psi|kpa|mpa|v|a|hz|khz|mhz|kw|mw|rpm|hour|hours|hrs?|min|minutes?|%)\b|
        \s*บาร์
    )?
    (?!\w)
    """,
    re.IGNORECASE | re.VERBOSE,
)

_UNIT_ALIASES = {
    "c": "c",
    "°c": "c",
    "℃": "c",
    "degree": "c",
    "degrees": "c",
    "deg": "c",
    "°": "c",
    "f": "f",
    "k": "k",
    "บาร์": "bar",
}


@dataclass(frozen=True)
class NumericToken:
    value: float
    unit: str | None
    raw: str


def normalize_numeric_text(text: str) -> str:
    return (text or "").translate(_THAI_DIGIT_MAP)


def _normalize_unit(unit: str | None) -> str | None:
    if not unit:
        return None
    cleaned = unit.strip().lower().replace(" ", "")
    if cleaned in {"°c", "℃"}:
        return "c"
    if cleaned.startswith("°") and len(cleaned) == 2 and cleaned[1] in {"c", "f", "k"}:
        return cleaned[1]
    for suffix in (
        "mm", "cm", "m", "km", "bar", "psi", "kpa", "mpa", "v", "a",
        "hz", "khz", "mhz", "kw", "mw", "rpm", "hour", "hours", "hrs",
        "hr", "min", "minutes", "minute", "%", "บาร์",
    ):
        if cleaned.endswith(suffix) or cleaned == suffix:
            return suffix.replace("hours", "hour").replace("minutes", "min").replace("minute", "min").replace("hrs", "hour").replace("hr", "hour").replace("บาร์", "bar")
    return _UNIT_ALIASES.get(cleaned, cleaned or None)


def _parse_value(raw: str) -> float:
    return float(raw.replace(",", ""))


def extract_numerics(text: str) -> list[NumericToken]:
    normalized = normalize_numeric_text(text)
    tokens: list[NumericToken] = []
    seen: set[tuple[float, str | None]] = set()
    for match in _NUMERIC_RE.finditer(normalized):
        raw = match.group("raw")
        unit_raw = match.group("unit")
        value = _parse_value(raw)
        unit = _normalize_unit(unit_raw)
        key = (round(value, 6), unit)
        if key in seen:
            continue
        seen.add(key)
        tokens.append(NumericToken(value=value, unit=unit, raw=match.group("raw")))
    return tokens


def _numeric_keys(tokens: list[NumericToken]) -> set[tuple[float, str | None]]:
    return {(round(token.value, 6), token.unit) for token in tokens}


# Unit-less integers ≤ this value are treated as list ordinals / section numbers
# and are not required to appear in the context. Only numbers with units (°C, RPM,
# bar, %, …) or large bare numbers (> threshold) are checked for grounding.
_ORDINAL_SKIP_THRESHOLD = 20

# Document locators ("หน้า 21 และ 53", "p. 148", "หัวข้อ 5.3", "ตาราง 2-4") cite
# WHERE a fact lives, not the fact itself. The page number usually comes from
# chunk metadata rather than chunk text, so requiring it to appear in the
# context suppressed fully-correct answers as numeric_grounding_fail. Masked in
# the ANSWER only — context numbers only ever widen the allowed set. A value
# claim ("85°C") elsewhere in the sentence is still enforced.
_LOCATOR_NUM = r"\d{1,4}(?:\.\d{1,3})?(?:\s*[-–]\s*\d{1,4}(?:\.\d{1,3})?)?"
_DOC_LOCATOR_RE = re.compile(
    r"""
    (?:
        หน้าที่|หน้า|บทที่|ข้อที่|ตารางที่|ตาราง|รูปที่|หัวข้อที่|หัวข้อ|
        pages?|pp\.?|p\.|sections?|sect\.|chapters?|tables?|figures?|figs?\.
    )
    \s*
    (?P<nums>NUM(?:\s*(?:,|และ|and|&|หรือ|or)\s*NUM)*)
    """.replace("NUM", _LOCATOR_NUM),
    re.IGNORECASE | re.VERBOSE,
)


def mask_document_locators(text: str) -> str:
    """Blank page/section/table references so they are not treated as claims."""
    return _DOC_LOCATOR_RE.sub(" ", text or "")


def answer_numerics_subset_of_context(
    answer: str,
    context: str,
    *,
    question: str | None = None,
) -> bool:
    """True when every substantive numeric in answer appears in context (unit-aware).

    Small unit-less integers (e.g. "1.", "2.", "3." in a bullet list) are skipped
    because they are list/section ordinals, not factual claims that the LLM could
    hallucinate in a meaningful way.  Numbers with units (85°C, 200 rpm, …) are
    always enforced regardless of magnitude.

    When ``question`` is given, numerics the USER wrote in the question are also
    allowed — restating "45 cSt" from "ถ้าน้ำมันเกียร์หนืดต่ำกว่า 45 cSt ใช้ต่อได้ไหม"
    is not a fabrication, and suppressing the whole answer over it produced
    false no-data. Callers must NOT pass the question for safety-intent or
    explicit-limit questions, where echoing the asker's number is exactly the
    confirmation-bias failure this gate exists to block.
    """
    answer_tokens = extract_numerics(mask_document_locators(answer))
    if not answer_tokens:
        return True
    allowed_keys = _numeric_keys(extract_numerics(context))
    if question:
        allowed_keys |= _numeric_keys(extract_numerics(question))
    for token in answer_tokens:
        # Skip unit-less small integers — almost certainly list or section ordinals.
        if token.unit is None and token.value == int(token.value) and token.value <= _ORDINAL_SKIP_THRESHOLD:
            continue
        key = (round(token.value, 6), token.unit)
        if key not in allowed_keys:
            if not any(abs(v - token.value) < 1e-6 for v, _ in allowed_keys):
                return False
    return True
