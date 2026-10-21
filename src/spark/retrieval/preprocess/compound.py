"""Compound-question UX helpers.

This is separate from multi-hop retrieval decomposition. Multi-hop decomposition
merges evidence for one answer; compound UX answers each user-visible question
separately so mixed prompts do not collapse into a single no-data response.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from spark.retrieval.scoring import _machine_ids_in_text, _registry_ids_in_text

SubQuestionKind = Literal[
    "chitchat",
    "external_live",
    "needs_scope",
    "needs_document_scope",
    "policy",
    "sensitive",
    "safety_emergency",
    "safety_procedure",
    "factory_operation",
    "machine_context",
    "out_of_scope",
    "ambiguous_action",
    "general_support",
    "document",
]


@dataclass(frozen=True)
class SubQuestion:
    text: str
    kind: SubQuestionKind


_GREETING_PREFIX_RE = re.compile(
    r"^\s*(สวัสดี|หวัดดี|hello|hi|hey)\s+(.+)$",
    re.IGNORECASE,
)

_CLAUSE_START_RE = re.compile(
    r"(?=(?:ผลบอลโลก|ผลบอล|บอลเมื่อคืน|บอลโลก|ราคาทอง|ทองขึ้น|ทองลง|ราคาหุ้น|หุ้น|"
    r"ฝนตก|อากาศ|ข่าว|หวย|"
    r"เปลี่ยนรหัสผ่าน|เคลมประกัน|แคนเซิลออเดอร์|ยกเลิก|ติดต่อเจ้าหน้าที่|"
    r"นโยบายลาป่วย|โปรโมชั่น|โปรโมชัน|"
    r"ที่\s+terminal|terminal\s+|เครื่องร้อน|อุณหภูมิ|วิธีแก้|วิธีแก้ไข|"
    r"error\s*\d+|alarm\s*\d+|สรุปเอกสาร|เปรียบเทียบ|เทียบ))",
    re.IGNORECASE,
)

_SOFT_SEPARATORS_RE = re.compile(
    r"\s*(?:[?？]|[,\n;；]|(?:\s+แล้ว\s+))\s*"
)

# Interrogative markers that make a clause read as a standalone question.
# Gates the general connective split below so it never breaks statements.
# "ไหม" needs the (?!้) guard or "กลิ่นไหม้" would count as a question.
_QUESTION_MARKER_RE = re.compile(
    r"(เท่าไหร่|เท่าไร|กี่|อะไร|ไหน|อย่างไร|ยังไง|เมื่อไหร่|เมื่อไร|ทำไม|"
    r"ไหม(?!้)|มั้ย|หรือไม่|หรือเปล่า|หรือยัง|"
    r"\?|？|\b(?:what|how|which|where|when|why|who)\b)",
    re.IGNORECASE,
)

# Clause-initial Thai connectives. In written Thai a space marks a clause
# boundary, so a connective PRECEDED by whitespace starts a new clause
# ("...เท่าไหร่ แล้วต้องใช้..."). Perfective/coordinating uses attach to the
# previous word instead ("เปิดเครื่องแล้ว รอ...") and never match here.
# Longer forms must come before their prefixes (แล้วก็ before แล้ว).
#
# English "and"/"then" are far riskier: "and" is the normal way to coordinate
# a compound NOUN phrase inside a single question ("voltage and current of
# the KSS controller?"), and that trailing "?" would satisfy the naive
# per-piece question-marker gate below for both halves. Thai question
# particles (เท่าไหร่/กี่/...) trail their clause, so splitting a false
# compound noun phrase there already fails the gate naturally — English
# wh-words front their clause instead, so only split on "and"/"then" when
# what follows immediately reads as the start of a new question clause
# (a wh-word or a fronted auxiliary/copula), never on a bare "and".
_CONNECTIVE_BOUNDARY_RE = re.compile(
    r"\s+(?:แล้วก็|และก็|แล้ว|และ|กับ|ส่วน|รวมถึง|พร้อมทั้ง|พร้อมกับ)"
    r"|\s+(?:and|then)(?=\s+(?:what|how|which|where|when|why|who|"
    r"is|are|was|were|does|do|did|can|could|would|will|should|has|have)\b)",
    re.IGNORECASE,
)

_EXTERNAL_LIVE_RE = re.compile(
    r"(ผลบอล|บอลโลก|บอลเมื่อคืน|บอลวันนี้|world\s*cup|ราคาทอง|ทองขึ้น|ทองลง|gold\s*price|"
    r"ราคาหุ้น|stock\s*price|หวย|lottery|ฝนตก|อากาศ(?:วันนี้)?|weather|"
    r"ข่าว(?:ล่าสุด|วันนี้)?|news|"
    r"วันนี้|ล่าสุด|ตอนนี้|current|latest|live)",
    re.IGNORECASE,
)

_DOC_DOMAIN_RE = re.compile(
    r"(เครื่อง|เครื่องจักร|machine|mc-\d+|terminal|แผนภาพ|ไฟฟ้า|wiring|diagram|"
    r"error|alarm|อุณหภูมิ|temperature|ร้อน|overheat|วิธีแก้|ซ่อม|คู่มือ|manual)",
    re.IGNORECASE,
)

_SCOPE_HINT_RE = re.compile(
    r"(terminal|แผนภาพ|ไฟฟ้า|wiring|diagram|เครื่องร้อน|(?<!พัก)ร้อน|overheat|"
    r"อุณหภูมิ|temperature|error\s*\d+|alarm\s*\d+|วิธีแก้|ซ่อม)",
    re.IGNORECASE,
)

_DOC_SCOPE_HINT_RE = re.compile(
    r"(สรุปเอกสาร|สรุปไฟล์|เอกสารนี้|ไฟล์นี้|this\s+document|this\s+file|summari[sz]e)",
    re.IGNORECASE,
)

_POLICY_QUESTION_RE = re.compile(
    r"(ไม่มีในเอกสาร|นอกเอกสาร|ถ้าไม่พบ|ถ้าไม่มีข้อมูล).*(เดา|มั่ว|ประมาณ|ตอบเอง)|"
    r"(เดา|มั่ว).*(ได้ไหม|ได้มั้ย|ให้หน่อย)",
    re.IGNORECASE,
)

_SENSITIVE_REQUEST_RE = re.compile(
    r"(เบอร์โทรส่วนตัว|โทรศัพท์ส่วนตัว|เบอร์.*(?:CEO|ผู้บริหาร)|(?:CEO|ผู้บริหาร).*เบอร์|"
    r"personal\s+phone|private\s+phone)|"
    r"(ซอร์สโค้ด|source\s*code|源码)",
    re.IGNORECASE,
)

_OUT_OF_SCOPE_RE = re.compile(
    r"(สูตรทำ|ทำอาหาร|ต้มยำ|ร้านอาหาร|อาหารทะเล|เผ็ด|แนะนำร้าน|recipe|restaurant)",
    re.IGNORECASE,
)

_AMBIGUOUS_ACTION_RE = re.compile(
    r"^(?:ขอ)?ยกเลิก(?:หน่อย|ให้หน่อย)?$|^cancel$",
    re.IGNORECASE,
)

# Whole-utterance phrases that legitimately mean two different domains
# (HR/office vs machinery) — ask which one instead of guessing.
_DOMAIN_AMBIGUOUS_RE = re.compile(
    r"^(?:ขอ|เปิด|ดู|เช็ค|อยากได้)?\s*(บันทึกเวลา|ระบบล็อก)\s*(?:หน่อย|ให้หน่อย|ครับ|ค่ะ)?\s*$",
    re.IGNORECASE,
)

# Company welfare / internal events — never machinery, and "Company Trip"
# must not be dragged into machine context by the electrical "trip" keyword.
_COMPANY_WELFARE_RE = re.compile(
    r"(ท่องเที่ยวประจำปี|เที่ยวประจำปี|company\s*trip|ทริปบริษัท|งานเลี้ยง|outing|"
    r"โรงอาหาร|เมนูอาหาร|เมนูกลางวัน|ยูนิฟอร์ม|ชุดฟอร์มพนักงาน)",
    re.IGNORECASE,
)

_GENERAL_SUPPORT_RE = re.compile(
    r"(เปลี่ยนรหัสผ่าน|รหัสผ่าน|password|เคลม|ประกัน|warranty|claim|"
    r"แคนเซิล|แคนเซิลออเดอร์|ยกเลิกออเดอร์|ออเดอร์|order|สมาชิก|membership|"
    r"แอคเคาท์|account|แอป|app|เงิน.*ตัด|ตัดเงิน|refund|คืนเงิน|"
    r"ศูนย์บริการ|ส่งซ่อม|ติดต่อใคร|ติดต่อเจ้าหน้าที่|เจ้าหน้าที่|"
    r"แพ็กเกจ|แพคเกจ|package|คุ้มกว่า|สินค้า|รุ่น\s*[A-Za-z0-9]|สีอะไร|มีสี|"
    r"โปรโมชัน|โปรโมชั่น|อัพเดทข้อมูล|อัปเดตข้อมูล|update|"
    r"นโยบายลาป่วย|ลาป่วย|ลาคลอด|ลาพักร้อน|สิทธิ์|เงินเดือน)",
    re.IGNORECASE,
)

_SAFETY_EMERGENCY_RE = re.compile(
    r"(แก๊ส|gas|สารเคมี|chemical|ไฟไหม้|ควัน|ระเบิด|explosion|รั่ว|leak|"
    r"คนเจ็บ|บาดเจ็บ|ไฟดูด|ช็อต|emergency|ฉุกเฉิน|"
    r"ปฐมพยาบาล|first\s*aid|เข้าตา|โดนตา|ล้างตา|ถูกผิวหนัง|โดนผิวหนัง|สูดดม|กลืน)",
    re.IGNORECASE,
)

# Asking ABOUT the emergency-stop device/procedure ("How do I emergency stop
# the KUKA robot?", "ปุ่มหยุดฉุกเฉินอยู่ตรงไหน") is a manual lookup — the E-stop
# chapter is exactly what the corpus documents. Only the bare words
# "emergency/ฉุกเฉิน" made these trip the canned incident lecture.
_ESTOP_LOOKUP_RE = re.compile(
    r"(e[-\s]?stop|emergency\s+stop|หยุดฉุกเฉิน|ปุ่มฉุกเฉิน|สวิตช์ฉุกเฉิน)",
    re.IGNORECASE,
)

# An incident actually in progress (or first-aid need) keeps the canned
# emergency answer even when the question also names the E-stop device.
_ACTIVE_HAZARD_RE = re.compile(
    r"(แก๊ส|gas|สารเคมี|chemical|ไฟไหม้|ควัน|ระเบิด|explosion|รั่ว|leak|"
    r"คนเจ็บ|บาดเจ็บ|ไฟดูด|ช็อต|"
    r"ปฐมพยาบาล|first\s*aid|เข้าตา|โดนตา|ล้างตา|ถูกผิวหนัง|โดนผิวหนัง|สูดดม|กลืน)",
    re.IGNORECASE,
)

_FIRST_AID_RE = re.compile(
    r"(ปฐมพยาบาล|first\s*aid|เข้าตา|โดนตา|ล้างตา|ถูกผิวหนัง|โดนผิวหนัง|สูดดม|กลืน)",
    re.IGNORECASE,
)

# Abnormal-overheat symptom: equipment too hot to touch / burning smell. This is
# a hazard report, not a spec question — answer "stop the machine safely" first.
# Kept tight so temperature-spec questions ("อุณหภูมิสูงสุดเท่าไหร่") never match.
_OVERHEAT_SYMPTOM_RE = re.compile(
    r"(ร้อนจี๋|ร้อนผิดปกติ|overheat|กลิ่นไหม้|กลิ่นเหม็นไหม้|"
    r"ร้อน\S{0,12}(?:จับ|แตะ|สัมผัส)ไม่ได้)",
    re.IGNORECASE,
)

# Hot work (welding/cutting/grinding with sparks). "เชื่อมแก๊ส/งานเชื่อม" — NOT a
# bare "เชื่อม", which would swallow I/O questions like "เชื่อมต่อไปที่ port อะไร".
_HOT_WORK_RE = re.compile(
    r"(hot\s*work|งานความร้อน|ใบอนุญาตทำงานความร้อน|เชื่อมแก๊ส|งานเชื่อม|ตัดแก๊ส|เจียรไฟ)",
    re.IGNORECASE,
)

# Respirator/PPE selection for a chemical — the correct answer is always
# "per that substance's SDS", never a guessed cartridge number.
_CHEMICAL_PPE_RE = re.compile(
    r"(หน้ากาก|respirator|ตลับกรอง|ไส้กรอง|cartridge|ถุงมือ|ppe)",
    re.IGNORECASE,
)

# Markers of DOING risky work — not of merely mentioning a part or the word
# "safety". Standalone "ใบมีด"/"ตัด"/"press"/"safety" turned informational spec
# questions ("ใบมีดเบอร์อะไร", "pressure เท่าไหร่", "Safety Data Sheet") into a
# canned LOTO lecture.
_SAFETY_PROCEDURE_RE = re.compile(
    r"(เปลี่ยนใบมีด|เครื่องตัด|เข้าไปในเครื่อง|guard|"
    r"lockout|tagout|loto|ทำงานขณะเครื่อง|bypass)",
    re.IGNORECASE,
)

# Reading a recorded RESULT ("inspection report ระบุผล guard interlock
# อย่างไร") is a document lookup, not doing risky work — it must reach
# retrieval, not the canned Safety-First lecture. Kept to result-lookup
# phrasing only so procedure requests ("เปลี่ยนใบมีดทำยังไง") stay intercepted.
_INSPECTION_RESULT_LOOKUP_RE = re.compile(
    r"(inspection|report|รายงาน|ผลตรวจ|ผลการตรวจ|ระบุผล|ผลของการตรวจ)",
    re.IGNORECASE,
)

# "ไลน์ 3"/"line 3" deliberately NOT here — machinery symptom reports name
# production lines all the time ("มอเตอร์ในไลน์ 1 ร้อน") and must reach
# retrieval, not an operations clarification.
_FACTORY_OPERATION_RE = re.compile(
    r"(กะ|shift|supervisor|หัวหน้า|รอบรถ|รถตู้|รับส่ง|"
    r"คลังสินค้า|เบิก|ใบอนุมัติ|อนุมัติ|เครื่องมือ|tool|ประแจ|schedule)",
    re.IGNORECASE,
)

_MACHINE_CONTEXT_RE = re.compile(
    r"(คู่มือ|manual|wiring|diagram|cnc|mitsubishi|abb|m80|error\s*code|e\d{3,}|"
    r"ไฮดรอลิก|hydraulic|เยิ้ม|รั่ว|leakage|โอเวอร์โหลด|overload|relay|"
    r"ตู้คอนโทรล|คอนโทรล|control|ทริป|trip|breaker|เบรกเกอร์|"
    r"boiler|หม้อต้ม|บาร์|bar|แบริ่ง|bearing|มอเตอร์|motor|"
    r"จาระบี|grease|ตลับลูกปืน|ปั๊ม|pump|สตาร์ทไม่ติด|สปีด|speed|"
    r"น้ำมันเกียร์|gear oil|ชั่วโมงทำงาน|เปิดเครื่องจักร|pre[- ]?operation|checklist|"
    r"เครื่อง(?:จักร)?(?:เบอร์)?\s*\d+|เบอร์\s*\d+)",
    re.IGNORECASE,
)

# An alarm/error code is as exact an anchor as an asset id — manuals index
# their alarm tables by these codes, including hex forms ("alarm 26h") that
# the identifier regex below can't see (digits-first, so no letter prefix).
# A question carrying one must reach retrieval, never a "ระบุบริบทเครื่องจักร"
# bounce-back.
_ALARM_CODE_RE = re.compile(
    r"(?:alarm|alm|error|err|fault)\s*(?:code\s*)?[0-9A-Fa-f]{1,4}h?\b"
    r"|\b[0-9A-Fa-f]{2,4}h\b",
    re.IGNORECASE,
)


def has_alarm_code(question: str) -> bool:
    return bool(_ALARM_CODE_RE.search(question or ""))


def alarm_codes(question: str) -> list[str]:
    """Alarm/error code mentions in the question ("alarm 26h", bare "26h")."""
    return [m.group(0) for m in _ALARM_CODE_RE.finditer(question or "")]


# Exact technical identifiers that scope retrieval on their own: a dotted
# PLC/IO tag (RES0.BELT_CALIB_SENSOR), a connector/pin/model code (CN7, M80,
# KR C5 → "C5"), or a drawing/document number (EE-07). Questions carrying one
# are the MOST specific a user can ask — bouncing them back with "ระบุบริบท
# เครื่องจักร" because the tag happens to contain "control"/"motor" refuses
# exactly the questions the corpus can answer. Exact-tag retrieval and the
# machine-conflict guard still scope the answer afterwards.
_SPECIFIC_IDENTIFIER_RE = re.compile(
    r"[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z0-9_]{2,}"
    r"|\b[A-Za-z]{1,4}\d{1,4}\b"
    r"|\b[A-Za-z]{1,4}-\d{1,5}\b"
    # multi-segment serials (CNC_VF3_2024, PUMP-HYDRO-01/02) — must contain a
    # digit so plain "I/O" or "on-line" don't count as identifiers
    r"|\b(?=[A-Za-z0-9_/-]*\d)[A-Za-z][A-Za-z0-9]*(?:[_/-][A-Za-z0-9]+)+\b"
    # All-caps hyphenated device tags whose segments carry no digit at all
    # (AZXD-SEP, AZD-KEP, BLE-D). Every branch above needs a digit next to the
    # letters, so these read as ordinary words: "ถ้า AZXD-SEP 1 เสีย มอเตอร์ไหน
    # กระทบ" scored zero identifiers, tripped the <40-char machine-context rule
    # on the word "มอเตอร์", and was bounced with "ระบุบริบทเครื่องจักร" instead
    # of retrieving — even though the tag names the device exactly. Requiring
    # uppercase plus a hyphen keeps ordinary text out ("on-line", "PLC-based").
    r"|\b[A-Z]{2,8}(?:-[A-Z0-9]{1,8})+\b"
)


def has_specific_identifier(question: str) -> bool:
    return bool(_SPECIFIC_IDENTIFIER_RE.search(question or ""))


def question_identifiers(question: str) -> list[str]:
    """Specific identifiers (PLC tags, serials, connector codes) in the question."""
    return [m.group(0) for m in _SPECIFIC_IDENTIFIER_RE.finditer(question or "")]


def _clean_part(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", (text or "").strip(" \t\r\n,;?？")).strip()
    cleaned = re.sub(r"\s*(?:แล้ว|และ)\s*$", "", cleaned).strip()
    cleaned = re.sub(r"^(?:แล้ว|และ)\s*", "", cleaned).strip()
    return cleaned


def _split_by_known_starts(text: str) -> list[str]:
    raw_matches = list(_CLAUSE_START_RE.finditer(text))
    matches = []
    for match in raw_matches:
        if matches:
            prev_start = matches[-1].start()
            prev_fragment = text[prev_start:match.start()].lower()
            # Avoid nested starts inside one clause: "ที่ terminal..." should
            # stay one question, and "วิธีแก้... error 5436" is one repair ask.
            if match.start() - prev_start < 8 or "วิธีแก้" in prev_fragment:
                continue
        matches.append(match)
    if len(matches) <= 1:
        return [_clean_part(text)] if _clean_part(text) else []

    parts: list[str] = []
    for idx, match in enumerate(matches):
        start = match.start()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        prefix = text[:start].strip() if idx == 0 else ""
        chunk = text[start:end]
        if prefix and prefix not in {"ช่วย", "ขอ", "อยาก", "ต้องการ"}:
            parts.append(_clean_part(prefix))
        elif prefix:
            chunk = f"{prefix}{chunk}"
        cleaned = _clean_part(chunk)
        if cleaned:
            parts.append(cleaned)
    return parts


# Continuation clauses shorter than this are elliptical follow-ons that lean
# on the previous clause for their topic ("...ลาพักร้อนไปแล้วกี่วัน และเหลืออีก
# กี่วัน" — "เหลืออีกกี่วัน" carries no topic of its own) and cannot be
# retrieved against standalone. Keep them attached.
_MIN_CONNECTIVE_CLAUSE_CHARS = 16


def _split_by_connectives(text: str) -> list[str]:
    """General fallback for compound questions the topic whitelist misses.

    Split at clause-initial connectives, but accept only when EVERY resulting
    clause reads as a standalone question (carries an interrogative marker) and
    every continuation clause is substantial enough to carry its own topic.
    Procedure statements ("ทำความสะอาดเสร็จ แล้วเปิดเครื่องได้เลยไหม") and noun
    coordinations ("เปรียบเทียบ MC-001 กับ MC-002") stay whole.
    """
    pieces = [_clean_part(p) for p in _CONNECTIVE_BOUNDARY_RE.split(text)]
    pieces = [p for p in pieces if p]
    if len(pieces) < 2:
        return [_clean_part(text)]
    if all(_QUESTION_MARKER_RE.search(p) for p in pieces) and all(
        len(p) >= _MIN_CONNECTIVE_CLAUSE_CHARS for p in pieces[1:]
    ):
        return pieces
    return [_clean_part(text)]


def split_compound_question(question: str) -> list[str]:
    """Split a user prompt into visible question units.

    Conservative: only returns multiple parts when there are strong separators,
    recognizable question starts, or clause-initial connectives where every
    clause is independently question-shaped. This avoids breaking normal Thai
    procedure questions that happen to contain "และ".
    """
    q = _clean_part(question)
    if not q:
        return []

    parts: list[str] = []
    greeting = _GREETING_PREFIX_RE.match(q)
    if greeting:
        parts.append(_clean_part(greeting.group(1)))
        q = _clean_part(greeting.group(2))

    for coarse in _SOFT_SEPARATORS_RE.split(q):
        coarse = _clean_part(coarse)
        if not coarse:
            continue
        known = _split_by_known_starts(coarse)
        if len(known) >= 2:
            parts.extend(known)
        else:
            parts.extend(_split_by_connectives(coarse))

    deduped: list[str] = []
    seen: set[str] = set()
    for part in parts or [q]:
        key = part.casefold()
        if len(part) < 2 or key in seen:
            continue
        deduped.append(part)
        seen.add(key)
    return deduped


def is_compound_question(question: str) -> bool:
    return len(split_compound_question(question)) >= 2


def is_external_live_question(question: str) -> bool:
    q = question or ""
    if not _EXTERNAL_LIVE_RE.search(q):
        return False
    return not _DOC_DOMAIN_RE.search(q)


def is_policy_question(question: str) -> bool:
    return bool(_POLICY_QUESTION_RE.search(question or ""))


def is_sensitive_request(question: str) -> bool:
    return bool(_SENSITIVE_REQUEST_RE.search(question or ""))


def is_out_of_scope_question(question: str) -> bool:
    return bool(_OUT_OF_SCOPE_RE.search(question or ""))


def is_ambiguous_action_question(question: str) -> bool:
    q = (question or "").strip()
    return bool(_AMBIGUOUS_ACTION_RE.search(q)) or bool(_DOMAIN_AMBIGUOUS_RE.search(q))


def is_company_welfare_question(question: str) -> bool:
    return bool(_COMPANY_WELFARE_RE.search(question or ""))


def is_general_support_question(question: str) -> bool:
    return bool(_GENERAL_SUPPORT_RE.search(question or ""))


def is_safety_emergency_question(question: str) -> bool:
    q = question or ""
    if _ESTOP_LOOKUP_RE.search(q) and not _ACTIVE_HAZARD_RE.search(q):
        return False
    # A question quoting an alarm code ("alarm 26h Motor overheat วิธีแก้") is
    # an alarm-table lookup — "overheat" there is the alarm's NAME, not a
    # reported symptom. Real hazards alongside the code still get the canned
    # emergency answer.
    if has_alarm_code(q) and not _ACTIVE_HAZARD_RE.search(q):
        return False
    return bool(
        _SAFETY_EMERGENCY_RE.search(q)
        or _OVERHEAT_SYMPTOM_RE.search(q)
        or _HOT_WORK_RE.search(q)
    )


def is_safety_procedure_question(question: str) -> bool:
    q = question or ""
    if _INSPECTION_RESULT_LOOKUP_RE.search(q):
        return False
    return bool(_SAFETY_PROCEDURE_RE.search(q))


def is_factory_operation_question(question: str) -> bool:
    return bool(_FACTORY_OPERATION_RE.search(question or ""))


def is_machine_context_question(question: str) -> bool:
    return bool(_MACHINE_CONTEXT_RE.search(question or ""))


# Keyword clarifications are for short symptom fragments with nothing to
# search on. Longer questions carry enough content to retrieve against —
# bouncing them back with "ระบุบริบทเครื่องจักร" both refuses answerable
# questions and (when the corpus has no such document) falsely implies the
# answer exists if the user just names a machine. Let retrieval decide;
# no-data already suggests specifying a machine code.
_MAX_KEYWORD_CLARIFY_CHARS = 40


def needs_scope_clarification(
    question: str,
    *,
    machine_id: str | None = None,
    known_machine_ids: set[str] | None = None,
) -> bool:
    q = question or ""
    if machine_id or _machine_ids_in_text(q) or has_specific_identifier(q):
        return False
    if has_alarm_code(q):
        return False
    if known_machine_ids and _registry_ids_in_text(q, known_machine_ids):
        return False
    if len(q.strip()) >= _MAX_KEYWORD_CLARIFY_CHARS:
        return False
    return bool(_SCOPE_HINT_RE.search(q))


def needs_document_scope_clarification(question: str) -> bool:
    return bool(_DOC_SCOPE_HINT_RE.search(question or ""))


def classify_subquestion(
    question: str,
    *,
    machine_id: str | None = None,
    known_machine_ids: set[str] | None = None,
) -> SubQuestion:
    from spark.retrieval.preprocess.adaptive import classify_retrieval_need

    q = _clean_part(question)
    adaptive = classify_retrieval_need(q)
    if adaptive.decision != "retrieve":
        return SubQuestion(q, "chitchat")
    if is_policy_question(q):
        return SubQuestion(q, "policy")
    if is_sensitive_request(q):
        return SubQuestion(q, "sensitive")
    if is_safety_emergency_question(q):
        return SubQuestion(q, "safety_emergency")
    if is_safety_procedure_question(q):
        return SubQuestion(q, "safety_procedure")
    if is_out_of_scope_question(q):
        return SubQuestion(q, "out_of_scope")
    if is_ambiguous_action_question(q):
        return SubQuestion(q, "ambiguous_action")
    if is_external_live_question(q):
        return SubQuestion(q, "external_live")
    if is_company_welfare_question(q):
        return SubQuestion(q, "general_support")
    if needs_document_scope_clarification(q):
        return SubQuestion(q, "needs_document_scope")
    if is_machine_context_question(q):
        has_machine_scope = bool(
            machine_id
            or _machine_ids_in_text(q)
            or has_specific_identifier(q)
            or has_alarm_code(q)
            or (known_machine_ids and _registry_ids_in_text(q, known_machine_ids))
        )
        # A machine question that already names its target (asset id, model
        # code, PLC tag) is retrievable as-is — it must reach retrieval, not
        # fall through to the general-support intercepts, whose "รุ่น X" branch
        # would misread "เครื่อง CNC รุ่น X-500" as a product/pricing question.
        if has_machine_scope:
            return SubQuestion(q, "document")
        if len(q) < _MAX_KEYWORD_CLARIFY_CHARS:
            return SubQuestion(q, "machine_context")
    if is_factory_operation_question(q):
        return SubQuestion(q, "factory_operation")
    if is_general_support_question(q):
        return SubQuestion(q, "general_support")
    if needs_scope_clarification(q, machine_id=machine_id, known_machine_ids=known_machine_ids):
        return SubQuestion(q, "needs_scope")
    return SubQuestion(q, "document")


def policy_answer(question: str, *, compact: bool = False) -> str:
    if compact:
        return (
            "ไม่ควรเดาครับ ถ้าไม่มีหลักฐานในเอกสาร Neo ควรบอกว่าไม่พบข้อมูล "
            "และแนะนำให้เพิ่มเอกสารหรือระบุขอบเขตให้ชัดขึ้น"
        )
    return (
        f"เรื่อง “{question}” ไม่ควรให้ Neo เดาหรือเติมข้อมูลเองครับ "
        "ถ้าไม่มีหลักฐานในเอกสาร ระบบควรตอบว่าไม่พบข้อมูล พร้อมแนะนำให้เพิ่มเอกสาร "
        "ระบุรหัสเครื่องจักร รุ่นเครื่อง รหัสเอกสาร หรือเลข drawing/manual เพื่อค้นต่อให้ตรงจุด"
    )


def sensitive_request_answer(question: str, *, compact: bool = False) -> str:
    if "ซอร์ส" in question or "source" in question.lower():
        base = (
            "ขออภัยครับ ผมไม่สามารถให้ซอร์สโค้ดหรือข้อมูลภายในที่ไม่ได้อยู่ในเอกสารที่อนุญาตได้ "
            "ถ้าต้องการเอกสารทางเทคนิค กรุณาระบุชื่อระบบ โมดูล หรือเอกสารที่มีสิทธิ์เข้าถึง"
        )
    else:
        base = (
            "ขออภัยครับ ผมไม่สามารถให้ข้อมูลส่วนตัวของบุคคล เช่น เบอร์โทรส่วนตัว ได้ "
            "ถ้าต้องการติดต่อองค์กร กรุณาระบุว่าต้องการช่องทางกลาง เช่น อีเมล แชต หรือเบอร์ฝ่ายที่เกี่ยวข้อง"
        )
    return base if not compact else base.split(" ถ้า")[0]


def safety_emergency_answer(question: str, *, compact: bool = False) -> str:
    if _FIRST_AID_RE.search(question or ""):
        # Universal first-aid guidance (ANSI/OSHA-standard, substance-independent)
        # — a first-aid question must get first aid immediately, never a request
        # for a machine code.
        return (
            "ปฐมพยาบาลก่อนเลยครับ:\n"
            "1. สารเคมี/น้ำมันเข้าตา — ล้างตาด้วยน้ำสะอาดหรือจุดล้างตาฉุกเฉิน (eyewash) ต่อเนื่องอย่างน้อย 15 นาที "
            "ห้ามขยี้ตา ถอดคอนแทคเลนส์ออกถ้าทำได้\n"
            "2. ถูกผิวหนัง — ถอดเสื้อผ้าที่เปื้อน แล้วล้างผิวด้วยน้ำสะอาดปริมาณมาก\n"
            "3. สูดดม — ย้ายผู้ป่วยไปที่อากาศถ่ายเท\n"
            "4. รีบพบแพทย์หรือห้องพยาบาลทันที และแจ้งหัวหน้างาน/ทีม EHS\n\n"
            "จากนั้นตรวจสอบเอกสาร SDS (Safety Data Sheet) ของสารนั้นเพื่อดูคำแนะนำเฉพาะครับ "
            "ถ้ามีเอกสาร SDS ในระบบ ระบุชื่อสารหรือเอกสารมาได้เลย Neo จะช่วยค้นให้ครับ"
        )
    if _OVERHEAT_SYMPTOM_RE.search(question or ""):
        # A hazard symptom must get "stop the machine" — never a generated
        # "no need to shut down" from an unrelated manual excerpt.
        return (
            "ควรหยุดเครื่องครับ อุปกรณ์ที่ร้อนจนสัมผัสไม่ได้ถือเป็นความผิดปกติที่เสี่ยงอันตราย:\n"
            "1. หยุดเครื่องตามขั้นตอนปกติ — ถ้ามีควัน กลิ่นไหม้ หรือเสียงผิดปกติร่วมด้วย "
            "ให้กดหยุดฉุกเฉิน (E-Stop) และแจ้งทันที\n"
            "2. อย่าสัมผัสตัวอุปกรณ์ กันคนออกจากบริเวณ และรอให้เย็นลงก่อนเข้าตรวจ\n"
            "3. แจ้งช่างซ่อมบำรุง/หัวหน้างานให้หาสาเหตุ เช่น โหลดเกิน ช่องระบายอากาศอุดตัน "
            "หรือแบริ่งเสีย ก่อนเปิดใช้งานอีกครั้ง\n\n"
            "ระบุรหัสเครื่องหรือรุ่นอุปกรณ์มาได้เลย Neo จะช่วยค้นคู่มือและค่าที่ยอมรับได้ให้ครับ"
        )
    if _HOT_WORK_RE.search(question or ""):
        return (
            "ต้องขอใบอนุญาตทำงานความร้อน (Hot Work Permit) ก่อนเริ่มงานครับ "
            "งานเชื่อม ตัด หรือเจียรที่เกิดประกายไฟใกล้คลังพัสดุหรือวัสดุไวไฟเข้าข่ายงานความร้อนโดยตรง:\n"
            "1. ขอ Hot Work Permit จาก จป./ทีม EHS ให้เรียบร้อยก่อนเริ่มงานทุกครั้ง\n"
            "2. เคลียร์วัสดุไวไฟออกจากรัศมีงานตามแนวปฏิบัติมาตรฐาน (ทั่วไปประมาณ 11 เมตร) "
            "หรือคลุมด้วยวัสดุกันไฟ\n"
            "3. เตรียมถังดับเพลิงและจัดผู้เฝ้าระวังไฟ (fire watch) ตลอดงานและช่วงเฝ้าระวังหลังจบงาน\n\n"
            "เงื่อนไขเฉพาะของโรงงานให้ยึดตามแบบฟอร์ม permit ของหน่วยงานครับ "
            "ถ้ามีเอกสารขั้นตอนในระบบ Neo ช่วยค้นให้ได้ครับ"
        )
    if _CHEMICAL_PPE_RE.search(question or ""):
        return (
            "การเลือกหน้ากาก/ตลับกรองต้องยึดตาม SDS ของสารตัวนั้นครับ เดาเบอร์เองไม่ได้ "
            "เพราะตลับกรองผิดชนิดจะไม่กรองสารนั้นเลย:\n"
            "1. กลิ่นฉุนแรงผิดปกติ — อย่าอยู่ดมต่อ ให้ออกจากพื้นที่ เปิดระบายอากาศ "
            "และแจ้งหัวหน้างาน/ทีม EHS ตรวจสอบก่อน\n"
            "2. ดูฉลากข้างถังหรือรหัสสาร (UN Number) แล้วเปิด SDS หัวข้อ 8 "
            "(Exposure Controls / PPE) — จะระบุชนิดตลับกรองที่ถูกต้อง "
            "เช่น ไอระเหยอินทรีย์ (organic vapor) หรือกรด/แก๊ส\n"
            "3. ถ้าไม่ทราบชนิดสารหรือฉลากหาย ห้ามเข้าไปจัดการเอง ให้ทีม EHS ตรวจสอบครับ\n\n"
            "ถ้าบอกชื่อสารหรือมีเอกสาร SDS ในระบบ Neo จะช่วยค้นชนิดตลับกรองที่ถูกต้องให้ครับ"
        )
    return (
        "ความปลอดภัยมาก่อนครับ: ให้หยุดงานในพื้นที่ แจ้งหัวหน้างาน/ทีม EHS ทันที "
        "กันคนออกจากจุดเสี่ยง และทำตามแผนฉุกเฉินของโรงงานก่อนค้นคู่มือหรือซ่อมบำรุง "
        "ถ้ามีคนเจ็บ ไฟไหม้ แก๊สรั่ว หรือสารเคมีรั่ว ให้ใช้ช่องทางฉุกเฉินของโรงงานทันที "
        "ผมจะไม่ให้ขั้นตอนซ่อมละเอียดโดยไม่มีเอกสารความปลอดภัยและผู้รับผิดชอบยืนยัน"
    )


def safety_procedure_answer(question: str, *, compact: bool = False) -> str:
    return (
        "งานนี้เข้าข่ายงานเสี่ยง ต้องทำ Safety First ก่อนครับ: หยุดเครื่อง แยกพลังงาน "
        "ทำ Lockout/Tagout ตรวจว่าไม่มีพลังงานค้าง และให้ผู้มีสิทธิ์อนุมัติงานก่อนเริ่ม "
        "กรุณาระบุรหัสเครื่องจักร รุ่นเครื่อง หรือเอกสาร SOP/LOTO ที่ต้องใช้อ้างอิง "
        "แล้วผมจะตอบตามเอกสารเท่านั้น"
    )


def factory_operation_answer(question: str, *, compact: bool = False) -> str:
    q = question or ""
    if re.search(r"(กะ|shift|supervisor|หัวหน้า|รอบรถ|รถตู้|รับส่ง|คืนนี้|วันนี้|เย็น)", q, re.IGNORECASE):
        return (
            "คำถามนี้เป็นข้อมูลปฏิบัติการ/ตารางเวลาปัจจุบันครับ ต้องมีตารางกะ ตารางรถ หรือเอกสารประกาศล่าสุดในระบบก่อน "
            "กรุณาระบุวันที่ ไลน์/จุดรับส่ง และแหล่งข้อมูลที่ต้องการอ้างอิง ผมจะไม่เดาชื่อคนหรือเวลารถเอง"
        )
    return (
        "คำถามนี้เกี่ยวกับขั้นตอนโรงงาน/คลัง/การอนุมัติครับ กรุณาระบุเอกสารนโยบาย หน่วยงาน คลังสินค้า "
        "หรือประเภทเครื่องมือที่ต้องการอ้างอิง ผมจะตอบตามเอกสารที่มีเท่านั้น"
    )


def machine_context_answer(question: str, *, compact: bool = False) -> str:
    q = question or ""
    hints = ["รหัสเครื่องจักรหรือ asset id", "รุ่น/ผู้ผลิต", "ไลน์หรือพื้นที่", "ชื่อเอกสาร/manual/drawing"]
    if re.search(r"(error|alarm|e\d{3,})", q, re.IGNORECASE):
        hints.insert(1, "รหัส error/alarm พร้อมรุ่นเครื่อง")
    if re.search(r"(wiring|diagram|ตู้คอนโทรล|terminal)", q, re.IGNORECASE):
        hints.insert(1, "เลข drawing หรือตู้/แผงที่เกี่ยวข้อง")
    if re.search(r"(สปีด|speed|น้ำมันเกียร์|ชั่วโมง|pre[- ]?operation|checklist|เปิดเครื่อง)", q, re.IGNORECASE):
        hints.insert(1, "รอบ PM หรือ SOP ที่ต้องการอ้างอิง")
    listed = " / ".join(dict.fromkeys(hints))
    return (
        f"เรื่อง “{question}” ต้องระบุบริบทเครื่องจักรให้ชัดก่อนครับ เช่น {listed} "
        "เพื่อให้ดึงคู่มือหรือเอกสารที่ถูกเล่ม และหลีกเลี่ยงการตอบผิดเครื่อง"
    )


def out_of_scope_answer(question: str, *, compact: bool = False) -> str:
    if compact:
        return "เรื่องนี้อยู่นอกขอบเขตเอกสารของระบบครับ กรุณาอัปโหลดเอกสารอ้างอิงหรือถามเรื่องงาน/สินค้า/องค์กรที่มีเอกสารรองรับ"
    return (
        f"เรื่อง “{question}” ยังอยู่นอกขอบเขตเอกสารที่ระบบนี้ใช้ตอบครับ "
        "ผมจะไม่เดาคำตอบเอง หากต้องการให้ช่วยวิเคราะห์ กรุณาอัปโหลดเอกสารอ้างอิงหรือระบุแหล่งข้อมูลที่ต้องการให้ใช้"
    )


def ambiguous_action_answer(question: str, *, compact: bool = False) -> str:
    q = (question or "").strip()
    if "บันทึกเวลา" in q:
        return (
            "“บันทึกเวลา” หมายถึงอะไรครับ ระหว่าง\n"
            "- บันทึกเวลาทำงานของพนักงาน (ลงเวลา/HR)\n"
            "- ชั่วโมงเดินเครื่องจักร (Running Hours) สำหรับงานซ่อมบำรุง\n"
            "ระบุเพิ่มอีกนิด แล้ว Neo จะค้นให้ตรงจุดครับ"
        )
    if "ระบบล็อก" in q:
        return (
            "“ระบบล็อก” หมายถึงอะไรครับ ระหว่าง\n"
            "- การล็อกอิน/เข้าใช้งานซอฟต์แวร์หรือระบบไอที\n"
            "- เครื่องจักรติด Interlock หรือระบบล็อกความปลอดภัย (LOTO)\n"
            "ระบุเพิ่มอีกนิด แล้ว Neo จะค้นให้ตรงจุดครับ"
        )
    return (
        "ต้องระบุสิ่งที่ต้องการยกเลิกก่อนครับ เช่น ออเดอร์ สมาชิก การจอง บริการ หรือคำขอล่าสุด "
        "ถ้ามีเลขอ้างอิงหรือชื่อแพ็กเกจให้ใส่มาด้วย ผมจะช่วยไล่ขั้นตอนจากเอกสารที่มีได้"
    )


def general_support_answer(question: str, *, compact: bool = False) -> str:
    q = question or ""
    if _COMPANY_WELFARE_RE.search(q):
        body = (
            "คำถามนี้เป็นเรื่องสวัสดิการ/กิจกรรมภายในบริษัทครับ Neo ตอบได้เฉพาะจากเอกสารหรือประกาศที่อัปโหลดไว้ในระบบ "
            "ตอนนี้ยังไม่พบประกาศเรื่องนี้ แนะนำสอบถามฝ่ายบุคคลหรือฝ่ายธุรการโดยตรง "
            "หรืออัปโหลดประกาศที่เกี่ยวข้องเข้าระบบ แล้ว Neo จะช่วยสรุปให้ครับ"
        )
        return body
    if re.search(r"(ลาป่วย|ลาคลอด|ลาพักร้อน|สิทธิ์|เงินเดือน)", q):
        body = (
            "คำถามนี้เกี่ยวกับสิทธิ์/HR ครับ หากไม่มีเอกสารนโยบายหรือข้อมูลวันลาของผู้ใช้ในระบบ "
            "ผมยังตอบตัวเลขหรือสิทธิ์เฉพาะบุคคลให้ไม่ได้ กรุณาระบุเอกสารนโยบาย ปีที่ต้องการ หรือให้ระบบเชื่อมต่อข้อมูล HR ที่เกี่ยวข้อง"
        )
    elif re.search(r"(แคนเซิล|ออเดอร์|order|สมาชิก|membership|คืนเงิน|refund|เงิน.*ตัด|ตัดเงิน|เคลม|ประกัน|ส่งซ่อม|ศูนย์บริการ)", q, re.IGNORECASE):
        body = (
            "คำถามนี้เกี่ยวกับบริการลูกค้า/คำสั่งซื้อครับ กรุณาระบุเลขออเดอร์ รุ่นสินค้า ช่องทางที่ซื้อ หรือเอกสารเงื่อนไขบริการ "
            "ตอนนี้ผมยังไม่มีหลักฐานพอจะยืนยันขั้นตอนเฉพาะให้ได้"
        )
    elif re.search(r"(รหัสผ่าน|password|แอคเคาท์|account|อัพเดทข้อมูล|อัปเดตข้อมูล|update)", q, re.IGNORECASE):
        body = (
            "คำถามนี้เกี่ยวกับบัญชีผู้ใช้ครับ กรุณาระบุระบบหรือหน้าจอที่ใช้งาน เช่น เว็บ แอป หรือพอร์ทัลพนักงาน "
            "ถ้ามีเอกสารคู่มือ/นโยบายความปลอดภัยในระบบ ผมจะตอบตามเอกสารนั้นเท่านั้น"
        )
    elif re.search(r"(แพ็กเกจ|แพคเกจ|package|สินค้า|รุ่น|สีอะไร|โปรโมชัน|โปรโมชั่น)", q, re.IGNORECASE):
        body = (
            "คำถามนี้เกี่ยวกับสินค้า/แพ็กเกจครับ กรุณาระบุเอกสารราคา รุ่นสินค้า หรือเงื่อนไขโปรโมชันที่ต้องการอ้างอิง "
            "ถ้าไม่มีเอกสารในระบบ ผมจะไม่เดาราคา สี หรือความคุ้มค่าเอง"
        )
    elif re.search(r"(ติดต่อเจ้าหน้าที่|เจ้าหน้าที่)", q):
        body = (
            "ต้องระบุช่องทางหรือทีมที่ต้องการติดต่อก่อนครับ เช่น บริการลูกค้า HR IT หรือฝ่ายซ่อมบำรุง "
            "หากมีเอกสารช่องทางติดต่อในระบบ ผมจะสรุปช่องทางที่พบให้"
        )
    else:
        body = (
            "คำถามนี้ต้องมีเอกสารหรือข้อมูลอ้างอิงเพิ่มเติมก่อนครับ กรุณาระบุระบบ สินค้า เอกสาร หรือเลขอ้างอิงที่เกี่ยวข้อง"
        )
    return body if not compact else body


def external_live_answer(question: str, *, compact: bool = False) -> str:
    if compact:
        return (
            "เป็นข้อมูลสดหรือนอกเอกสารครับ Neo ตอบจากเอกสารที่อัปโหลดเท่านั้น "
            "จึงยังไม่ดึงผลบอล ราคา ข่าว อากาศ หรือข้อมูลล่าสุดจากอินเทอร์เน็ตให้โดยตรง"
        )
    return (
        f"เรื่อง “{question}” เป็นข้อมูลสดหรือนอกเอกสารครับ "
        "Neo ตอบจากเอกสารที่อัปโหลดในระบบเท่านั้น และไม่ได้ดึงข้อมูลสดจากอินเทอร์เน็ต "
        "หากต้องการให้วิเคราะห์หัวข้อนี้ กรุณาอัปโหลดเอกสารที่มีข้อมูลดังกล่าวก่อนครับ"
    )


def scope_clarification_answer(question: str, *, compact: bool = False) -> str:
    if compact:
        return (
            "ต้องระบุขอบเขตเพิ่มก่อนครับ เช่น รหัสเครื่องจักร รุ่นเครื่อง "
            "รหัสเอกสาร หรือเลข drawing/manual"
        )
    return (
        f"เรื่อง “{question}” ยังต้องระบุขอบเขตเอกสารให้ชัดขึ้นครับ "
        "กรุณาระบุรหัสเครื่องจักร รุ่นเครื่อง รหัสเอกสาร หรือเลข drawing/manual "
        "เพื่อให้ Neo ค้นหาได้ตรงจุด"
    )


def document_scope_clarification_answer(question: str, *, compact: bool = False) -> str:
    if compact:
        return (
            "ต้องเลือกหรือระบุเอกสารก่อนครับ เช่น ชื่อไฟล์ รหัสเอกสาร "
            "ประเภทเอกสาร หรือขอบเขตโรงงาน/เครื่องจักรที่ต้องการสรุป"
        )
    return (
        f"เรื่อง “{question}” ยังต้องระบุเอกสารให้ชัดขึ้นครับ "
        "กรุณาเลือกไฟล์ในแชต หรือระบุชื่อไฟล์ รหัสเอกสาร ประเภทเอกสาร "
        "หรือขอบเขตโรงงาน/เครื่องจักรที่ต้องการให้ Neo สรุป"
    )
