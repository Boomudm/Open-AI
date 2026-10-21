"""Thai ↔ English manual term expansion — lexical leg only (Phase 7)."""

from __future__ import annotations

MANUAL_GLOSSARY: dict[str, tuple[str, ...]] = {
    "ลูกปืน": ("bearing", "bearings"),
    "อุณหภูมิ": ("temperature",),
    "ร้อน": ("overheat", "overheating", "hot", "temperature"),
    "พัดลม": ("fan", "cooling fan"),
    "ระบายความร้อน": ("cooling", "heat sink"),
    "สั่น": ("vibration", "vibrate"),
    "แรงดัน": ("pressure",),
    "น้ำมัน": ("oil", "lubrication"),
    "หล่อลื่น": ("lubrication", "lubricate"),
    "บำรุงรักษา": ("maintenance",),
    "ซ่อม": ("repair", "service"),
    "สตาร์ท": ("starter", "start"),
    "มอเตอร์": ("motor", "servo"),
    "เซนเซอร์": ("sensor",),
    "สายพาน": ("belt",),
    "ปั๊ม": ("pump",),
    "วาล์ว": ("valve",),
    "เบรก": ("brake",),
    # A circuit breaker is not a brake — without its own entry "เบรกเกอร์" only
    # matched "เบรก" and expanded a switchgear question with "brake", missing the
    # "Circuit Breaker" rows the wiring diagrams actually use. Longest-first
    # matching keeps the "เบรก" entry from also firing inside this one.
    "เบรกเกอร์": ("breaker", "circuit breaker"),
    "ไฟ": ("voltage", "power"),
    "กระแส": ("current",),
    "สายเคเบิล": ("cable", "connecting cable", "connecting cables", "cable set"),
    "สาย": ("cable",),
    "ยาว": ("length",),
    "ความยาว": ("length", "cable length"),
    "สูงสุด": ("maximum", "max"),
    "ตู้คอนโทรล": ("robot controller", "controller"),
    "ตู้ควบคุม": ("robot controller", "controller"),
    "หุ่นยนต์": ("robot", "manipulator"),
    "แบบไฟฟ้า": ("wiring diagram", "drawing", "diagram"),
    "สกรู": ("screw", "screws", "TORX"),
    "ขัน": ("fasten", "unscrew", "tighten"),
    "ลม": ("air",),
    "น้ำ": ("water",),
    "สูญญากาศ": ("vacuum", "vacuum generator", "vacuum gen"),
    # Spec-sheet lookups — Thai questions against English-only datasheets.
    "น้ำหนัก": ("weight",),
    # "หนัก" is how the question is usually phrased ("หุ่นยนต์หนักเท่าไร"); the
    # noun "น้ำหนัก" is the rarer form. Longest-first matching keeps this from
    # firing a second time inside "น้ำหนัก".
    "หนัก": ("weight",),
    "กิโลกรัม": ("kg", "weight"),
    "ขนาด": ("dimensions", "size"),
    "ความเร็ว": ("speed", "rpm"),
    "รอบ": ("rpm", "speed"),
    "กำลังไฟ": ("power", "rated power"),
    "แบตเตอรี่": ("battery",),
    "ฟิวส์": ("fuse",),
    "แผงวงจร": ("circuit board", "board"),
    # Wiring-diagram vocabulary — the vision analyses keep device/terminal/net
    # labels in Latin script even though the prose is Thai, so a Thai question
    # needs the English/label form on the lexical leg to hit the connection
    # tables and the Net/Shared-Bus index.
    "เทอร์มินอล": ("terminal",),
    "เทอมินอล": ("terminal",),
    "ขั้วต่อ": ("terminal", "connector"),
    "จุดต่อสาย": ("terminal", "terminal block"),
    "กราวด์": ("GND", "ground"),
    "สายดิน": ("GND", "PE", "ground", "protective earth"),
    "รีเลย์": ("relay",),
    "คอนแทคเตอร์": ("contactor",),
    "แมกเนติก": ("contactor", "magnetic contactor"),
    "โซลินอยด์": ("solenoid", "solenoid valve"),
    "หม้อแปลง": ("transformer",),
    "เพาเวอร์ซัพพลาย": ("power supply",),
    "พาวเวอร์ซัพพลาย": ("power supply",),
    "แหล่งจ่ายไฟ": ("power supply", "power source"),
    "อินเวอร์เตอร์": ("inverter", "drive"),
    "ไดรฟ์": ("drive", "servo drive"),
    "เซอร์โว": ("servo", "servo drive", "servo motor"),
    "เมนไฟ": ("main power", "incoming power"),
    "ไฟเข้า": ("incoming power", "power input"),
    "เฟส": ("phase", "L1", "L2", "L3"),
    "นิวทรัล": ("neutral", "N"),
    "ลัดวงจร": ("short circuit", "short"),
    "ช็อต": ("short circuit", "short"),
    "วงจร": ("circuit",),
    "สายไฟ": ("wire", "cable"),
    "เดินสาย": ("wiring", "wire routing"),
    "ไล่สาย": ("trace", "wiring", "connection"),
    "ไล่วงจร": ("trace", "circuit"),
    "แผงไฟ": ("panel", "distribution panel"),
    "ตู้ไฟ": ("panel", "control panel", "cabinet"),
    "สวิตช์": ("switch",),
    "ปุ่มกด": ("push button", "button"),
    "หลอดไฟสัญญาณ": ("pilot lamp", "indicator"),
    "ไฟสัญญาณ": ("indicator", "pilot lamp", "LED"),
    "การรับประกัน": ("warranty",),
    "รับประกัน": ("warranty",),
    "ติดตั้ง": ("installation", "install", "mounting"),
    "คู่มือ": ("manual",),
    "อะไหล่": ("spare part", "parts"),
    "ข้อผิดพลาด": ("error", "fault"),
    "สัญญาณเตือน": ("alarm", "warning"),
    "เตือน": ("alarm", "warning"),
    "กระพริบ": ("blink", "blinking", "LED"),
    "ขั้นตอน": ("procedure", "steps"),
    "ตรวจสอบ": ("inspection", "check"),
    # HR / welfare / policy — mixed Thai-English handbooks and policy sheets.
    "เงินเดือน": ("salary", "payroll"),
    "โบนัส": ("bonus",),
    "สวัสดิการ": ("welfare", "benefits"),
    "ประกัน": ("insurance",),
    "วันลา": ("leave", "leave days"),
    "ลาป่วย": ("sick leave",),
    "ลากิจ": ("personal leave",),
    "ลาพักร้อน": ("annual leave", "vacation"),
    "กะทำงาน": ("shift", "work shift"),
    "เข้ากะ": ("shift",),
    "ค่าล่วงเวลา": ("overtime", "OT"),
    "โอที": ("overtime", "OT"),
}


def expand_lexical_variants(query: str) -> str:
    """Append English equivalents for known Thai manual terms (lexical search only)."""
    text = (query or "").strip()
    if not text:
        return text
    extras: list[str] = []
    lower = text.lower()
    # Longest key first, blanking each hit as it matches. Thai is unspaced, so a
    # short key can sit inside an unrelated longer one — "น้ำ" (water) inside
    # "น้ำหนัก" (weight) — and a plain substring scan would expand a question
    # about weight with "water", pulling the lexical leg toward the wrong docs.
    # Blanking also lets "หนัก" coexist with "น้ำหนัก" without double-counting.
    remaining = text
    remaining_lower = lower
    for thai in sorted(MANUAL_GLOSSARY, key=len, reverse=True):
        english_terms = MANUAL_GLOSSARY[thai]
        if thai in remaining or thai.lower() in remaining_lower:
            extras.extend(english_terms)
            remaining = remaining.replace(thai, " ")
            remaining_lower = remaining_lower.replace(thai.lower(), " ")
    if not extras:
        return text
    unique = sorted({t for t in extras if t.lower() not in lower})
    if not unique:
        return text
    return f"{text} {' '.join(unique)}"
