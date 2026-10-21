"""Query feature extraction for intent routing."""

from __future__ import annotations

import re

from spark.retrieval.lexical.tokenize_industrial import (
    extract_symbolic_names,
    has_plc_tag,
)

_PART_NUMBER_RE = re.compile(
    r"\b(?:SKF[- ]?\d{3,5}|ISO[- ]?\d+|6205|6308|PN[- ]?\d{3,6}|[A-Z]{2,8}\d[A-Z0-9]*\d[A-Z0-9]*(?:-\d+)?)\b",
    re.IGNORECASE,
)
_ALARM_CODE_RE = re.compile(r"\b(?:E|ALM|ERR|F)[- ]?\d{2,5}\b", re.IGNORECASE)
_LOTO_RE = re.compile(
    r"\b(?:loto|lockout|tagout|lock.?out|tag.?out|ล็อค.?เอาท์|ล็อก.?เอาท์)\b",
    re.IGNORECASE,
)
_SYMPTOM_RE = re.compile(
    r"(?:ร้อน|overheat|temperature|อุณหภูมิ|สั่น|vibrat|alarm|error|fault|เสียง|leak|รั่ว|pressure|แรงดัน)",
    re.IGNORECASE,
)
_PROCEDURE_RE = re.compile(
    r"(?:ขั้นตอน|วิธี|procedure|how to|ต้องทำ|maintenance|บำรุง|ซ่อม|replace|install|ตรวจสอบ)",
    re.IGNORECASE,
)
_IO_MAPPING_CONTEXT_RE = re.compile(
    r"(?:symbolic\s*link|symlink|map(?:ped|ping)?|modbus|register|hardware\s*port|"
    r"เชื่อม|ต่อกับ|สัญญาณ|พารามิเตอร์|รีจิสเตอร์)",
    re.IGNORECASE,
)
_DRAWING_RE = re.compile(
    r"(?:wiring\s*diagram|drawing|diagram|แบบไฟฟ้า|"
    r"air\s*valve|water\s*valve|vacuum\s*(?:gen|generator)|"
    r"disk\s*\d+|spd[-_\s]*ctrl)",
    re.IGNORECASE,
)
_MANUAL_LOOKUP_RE = re.compile(
    r"(?:สายเคเบิล|ตู้คอนโทรล|ตู้ควบคุม|หุ่นยนต์|ความยาว|ยาวได้|กี่เมตร|"
    r"connecting\s*cable|cable\s*length|robot\s*controller|"
    r"interface\s*board|kr\s*c5|non-excitation|excitation)",
    re.IGNORECASE,
)
# How a technician phrases a connectivity/trace question about a wiring
# diagram without ever saying "diagram": where does it connect, what feeds it,
# what shares its bus, what goes down with it. Deliberately excludes generic
# troubleshooting verbs (เช็ค/ตรวจสอบ/ไม่หมุน/ไม่ทำงาน) — those questions are
# often answered better by the machine manual, and the connectivity route
# leans retrieval toward drawing chunks.
_WIRING_CONNECTIVITY_RE = re.compile(
    r"(?:ต่อกับ|ต่อไป|ต่ออยู่|ต่อที่|ต่อร่วม|ต่อเข้า|เชื่อมกับ|เชื่อมต่อ|"
    r"รับไฟ|จ่ายไฟ|ป้อนไฟ|เลี้ยงไฟ|ไฟเข้า|ไฟออก|ไฟเลี้ยง|แหล่งจ่าย|ตัดไฟ|"
    r"ไล่สาย|ไล่วงจร|เดินสาย|สายเบอร์|เบอร์สาย|เส้นทางไฟ|"
    r"เทอร์มินอล|เทอมินอล|ขั้ว|ขา\s?\d|กราวด์|สายดิน|บัส|รางไฟ|เฟส|"
    r"กระทบ|ลัดวงจร|ช็อต|ชอร์ต|"
    r"อยู่(?:ใน)?แบบ|แบบหน้าไหน|อยู่หน้าไหน|หน้าไหนของแบบ|"
    r"which\s+(?:page|sheet)|what\s+(?:page|sheet)|"
    r"terminal|connected?\s*to|wire\s*(?:no|number)|trace|"
    r"power(?:ed)?\s*(?:from|by)|feeds?|supply\s*from|shares?\s*(?:bus|net))",
    re.IGNORECASE,
)
# Wire-number phrases are their own anchor: "สายเบอร์ 205 ไปไหน" names the
# conductor directly, no device tag needed.
_WIRE_NUMBER_PHRASE_RE = re.compile(
    r"(?:สายเบอร์|เบอร์สาย|wire\s*(?:no\.?|number))\s*\S", re.IGNORECASE
)
# Electrical-device words that anchor a connectivity question when no printed
# tag is present ("ไฟเข้าตู้มาจากเบรกเกอร์ตัวไหน").
_ELECTRICAL_DEVICE_WORD_RE = re.compile(
    r"(?:เบรกเกอร์|รีเลย์|ฟิวส์|มอเตอร์|หม้อแปลง|โซลินอยด์|คอนแทคเตอร์|แมกเนติก|"
    r"เพาเวอร์ซัพพลาย|พาวเวอร์ซัพพลาย|อินเวอร์เตอร์|ไดรฟ์|เซอร์โว|ตู้ไฟ|"
    r"breaker|relay|fuse|contactor|transformer|solenoid|inverter|drive|servo|"
    r"power\s*supply|motor)",
    re.IGNORECASE,
)


def has_part_number(text: str) -> bool:
    return bool(_PART_NUMBER_RE.search(text or ""))


def has_alarm_code(text: str) -> bool:
    return bool(_ALARM_CODE_RE.search(text or ""))


def has_loto_terms(text: str) -> bool:
    return bool(_LOTO_RE.search(text or ""))


def has_symptom_terms(text: str) -> bool:
    return bool(_SYMPTOM_RE.search(text or ""))


def has_procedure_terms(text: str) -> bool:
    return bool(_PROCEDURE_RE.search(text or ""))


def has_io_mapping_terms(text: str) -> bool:
    raw = text or ""
    if has_plc_tag(raw):
        return True
    return bool(_IO_MAPPING_CONTEXT_RE.search(raw) and extract_symbolic_names(raw))


def has_drawing_terms(text: str) -> bool:
    return bool(_DRAWING_RE.search(text or ""))


def has_wiring_connectivity_terms(text: str) -> bool:
    """Connectivity/trace question aimed at a wiring diagram, phrased without
    the word "diagram" — e.g. "M18 ต่อกับอะไร", "X1:5 ไปไหน", "ถ้า K1 เสีย
    กระทบอะไร". Requires connectivity phrasing anchored by a concrete subject:
    a device tag / terminal / rail token, or an electrical-device word. The
    anchor keeps generic prose ("ต่อไปทำอะไรดี") out of the drawing route.
    """
    raw = text or ""
    if not _WIRING_CONNECTIVITY_RE.search(raw):
        return False
    if _WIRE_NUMBER_PHRASE_RE.search(raw) or _ELECTRICAL_DEVICE_WORD_RE.search(raw):
        return True
    from spark.retrieval.lexical.tokenize_industrial import extract_industrial_tokens

    return any(not token.isdigit() for token in extract_industrial_tokens(raw, limit=8))


def has_manual_lookup_terms(text: str) -> bool:
    return bool(_MANUAL_LOOKUP_RE.search(text or ""))
