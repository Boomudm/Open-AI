from __future__ import annotations

import re
from dataclasses import dataclass

TOPIC_KEYWORDS: list[tuple[str, list[str]]] = [
    ("bearing", ["bearing", "แบริ่ง", "ลูกปืน", "ลูกปืนกล"]),
    ("overheat", ["overheat", "ร้อน", "อุณหภูมิ", "ความร้อน", "hot"]),
    ("leak", ["leak", "รั่ว", "รั่วซึม", "สารเคมี", "น้ำมันรั่ว"]),
    ("vibration", ["vibration", "สั่น", "สั่นสะเทือน", "vibrate"]),
    ("pm_schedule", ["pm", "บำรุงรักษา", "maintenance schedule", "ตารางบำรุง"]),
    ("oil", ["oil", "น้ำมัน", "หล่อลื่น", "lubricat"]),
    ("belt", ["belt", "สายพาน", "chain", "โซ่"]),
    ("motor", ["motor", "มอเตอร์", "ไดร์ฟ"]),
    ("pump", ["pump", "ปั๊ม"]),
    ("safety", ["safety", "ความปลอดภัย", "ppe", "lockout", "loto"]),
    ("sop", ["sop", "ขั้นตอน", "procedure", "วิธีการ"]),
    ("electrical", ["electrical", "ไฟฟ้า", "วงจร", "breaker", "fuse"]),
]


@dataclass(frozen=True)
class TopicMatch:
    topic_label: str | None
    topic_confidence: float


def extract_topic(question: str) -> TopicMatch:
    q = question.lower().strip()
    if not q:
        return TopicMatch(None, 0.0)

    best_label: str | None = None
    best_score = 0.0

    for label, keywords in TOPIC_KEYWORDS:
        hits = sum(1 for kw in keywords if kw in q)
        if hits == 0:
            continue
        score = min(1.0, 0.5 + hits * 0.2)
        if score > best_score:
            best_score = score
            best_label = label

    if best_label:
        return TopicMatch(best_label, best_score)

    if re.search(r"[\u0E00-\u0E7F]{4,}", q):
        return TopicMatch("general_th", 0.3)
    if re.search(r"[a-z]{4,}", q):
        return TopicMatch("general_en", 0.3)

    return TopicMatch(None, 0.0)
