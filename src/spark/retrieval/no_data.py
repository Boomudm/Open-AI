# -*- coding: utf-8 -*-
"""Helpful no-data responses — say what WAS found and how to search better.

When retrieval cannot produce answerable evidence, a bare "ไม่พบข้อมูลในระบบ"
teaches the user nothing. For non-safety questions we instead tell them:
  1. that no direct answer was found (honest),
  2. the nearest documents the search DID reach (so they know coverage), and
  3. concrete ways to rephrase (machine code, alarm code, manual terminology).

Safety/LOTO questions keep the terse fail-closed NO_DATA_ANSWER — suggesting
"try rephrasing" around a lockout procedure is not acceptable.
"""

from __future__ import annotations

import re

from spark.retrieval.constants import NO_DATA_ANSWER
from spark.retrieval.models import RAGFilter, RetrievedDoc

_MAX_NEAR_MISS_TITLES = 3

# Recognized by synthesis._is_no_data_answer — keep prefixes stable.
UNKNOWN_MACHINE_PREFIX = "ไม่พบเครื่องจักรรหัส"
MACHINE_FILTER_MISMATCH_PREFIX = "เครื่องที่เลือกไม่ตรงกับคำถาม"
HELPFUL_NO_DATA_PREFIX = "ยังไม่พบข้อมูลที่ตรงกับคำถามนี้"

_MACHINE_ID_RE = re.compile(r"\b[A-Za-z]{1,12}-\d{1,8}\b")


def unknown_machine_answer(machine_id: str) -> str:
    return (
        f"{UNKNOWN_MACHINE_PREFIX} {machine_id} ในโรงงานนี้ครับ "
        "กรุณาตรวจสอบรหัสเครื่อง หรือเลือกเครื่องจักรจากรายการในระบบ "
        "แล้วถามใหม่อีกครั้งครับ"
    )


def machine_filter_mismatch_answer(question: str, selected_machine_id: str) -> str:
    mentioned = next(
        (
            value.upper()
            for value in _MACHINE_ID_RE.findall(question or "")
            if value.casefold() != selected_machine_id.casefold()
        ),
        None,
    )
    target = f"{mentioned} " if mentioned else "เครื่องอื่น "
    return (
        f"{MACHINE_FILTER_MISMATCH_PREFIX}ครับ: ตอนนี้เลือก {selected_machine_id} "
        f"แต่คำถามระบุ {target}กรุณาเปลี่ยนเครื่องในช่องเลือกด้านล่าง "
        "หรือยกเลิกตัวกรองเครื่อง แล้วส่งคำถามใหม่อีกครั้งครับ"
    )

_THAI_RE = re.compile(r"[฀-๿]")


def _doc_label(doc: RetrievedDoc) -> str | None:
    p = doc.payload or {}
    name = p.get("title") or p.get("source_file")
    if not name:
        return None
    label = str(name).strip()
    if not label:
        return None
    machine = str(p.get("machine_id") or "").strip()
    if machine:
        label = f"{label} ({machine})"
    return label


def _near_miss_labels(docs: list[RetrievedDoc]) -> list[str]:
    labels: list[str] = []
    seen: set[str] = set()
    for doc in docs:
        label = _doc_label(doc)
        if not label or label in seen:
            continue
        labels.append(label)
        seen.add(label)
        if len(labels) >= _MAX_NEAR_MISS_TITLES:
            break
    return labels


def _suggestions(question: str, rf: RAGFilter | None) -> list[str]:
    q = question or ""
    if re.search(r"(ลาป่วย|ลาคลอด|ลาพักร้อน|สิทธิ์|เงินเดือน|hr|leave)", q, re.IGNORECASE):
        return [
            "ระบุปี ชนิดการลา หรือเอกสารนโยบาย HR ที่ต้องการอ้างอิง",
            "ถ้าเป็นยอดวันลาส่วนบุคคล ต้องมีข้อมูลผู้ใช้หรือระบบ HR ที่เชื่อมต่ออยู่",
            "ลองถามแยกเป็นนโยบายรวม หรือยอดคงเหลือส่วนบุคคลทีละเรื่อง",
        ]
    if re.search(r"(รหัสผ่าน|password|แอคเคาท์|account|อัพเดทข้อมูล|อัปเดตข้อมูล|update)", q, re.IGNORECASE):
        return [
            "ระบุระบบหรือหน้าจอที่ต้องการใช้งาน เช่น เว็บ แอป หรือพอร์ทัลพนักงาน",
            "ระบุว่าต้องการขั้นตอน วิธีแก้ปัญหา หรือเงื่อนไขความปลอดภัย",
            "แนบหรือเลือกเอกสารคู่มือบัญชีผู้ใช้ที่ต้องการอ้างอิง",
        ]
    if re.search(r"(ออเดอร์|order|สมาชิก|membership|เคลม|ประกัน|warranty|claim|คืนเงิน|refund|ส่งซ่อม|ศูนย์บริการ)", q, re.IGNORECASE):
        return [
            "ระบุเลขออเดอร์ รุ่นสินค้า ช่องทางที่ซื้อ หรือประเภทบริการ",
            "ระบุว่าต้องการยกเลิก เคลม ส่งซ่อม คืนเงิน หรือสอบถามเงื่อนไข",
            "แนบหรือเลือกเอกสารเงื่อนไขบริการ/ประกันที่ต้องการอ้างอิง",
        ]
    # "รุ่น"/"สินค้า" appear in machine questions too ("เครื่อง CNC รุ่น X-500")
    # — those must get the machine search tips below, not package/pricing tips.
    is_machine_domain = re.search(
        r"(เครื่องจักร|เครื่อง|มอเตอร์|motor|cnc|machine|alarm|error|wiring|diagram|"
        r"manual|คู่มือ|ซ่อม|maintenance|terminal|plc)",
        q,
        re.IGNORECASE,
    )
    if not is_machine_domain and re.search(
        r"(แพ็กเกจ|แพคเกจ|package|สินค้า|รุ่น|โปรโมชัน|โปรโมชั่น|ราคา|สีอะไร|มีสี)", q, re.IGNORECASE
    ):
        return [
            "ระบุชื่อแพ็กเกจ รุ่นสินค้า หรือเอกสารราคา/โปรโมชัน",
            "ระบุเกณฑ์ที่ต้องการเทียบ เช่น ราคา ฟีเจอร์ ระยะเวลา หรือจำนวนผู้ใช้",
            "ถ้าเป็นข้อมูลล่าสุด ต้องมีเอกสารหรือข้อมูลโปรโมชันที่อัปเดตในระบบ",
        ]
    out: list[str] = []
    if rf is None or not getattr(rf, "machine_id", None):
        if not re.search(r"[A-Za-z]{1,4}-\d{2,5}", q):
            out.append("ระบุรหัสเครื่องจักรหรือรุ่นเครื่อง เพื่อจำกัดการค้นหา")
    if _THAI_RE.search(q):
        out.append(
            "ลองใช้คำศัพท์ตามคู่มือ (ภาษาอังกฤษ) เช่น ชื่อสัญญาณ รหัส alarm หรือชื่อรุ่นอะไหล่"
        )
    else:
        out.append("ลองระบุรุ่นเครื่อง รหัส alarm หรือชื่อเอกสารที่ต้องการค้น")
    out.append("แบ่งคำถามยาวเป็นคำถามสั้นๆ ทีละเรื่อง")
    return out[:3]


def build_no_data_answer(
    question: str,
    docs: list[RetrievedDoc],
    *,
    rf: RAGFilter | None = None,
    is_safety: bool = False,
) -> str:
    """Return a helpful no-data message; terse fail-closed text for safety."""
    if is_safety:
        return NO_DATA_ANSWER

    parts: list[str] = [
        f"{HELPFUL_NO_DATA_PREFIX}ในเอกสารที่เปิดอยู่ครับ"
    ]

    labels = _near_miss_labels(docs)
    if labels:
        listed = "\n".join(f"- {label}" for label in labels)
        parts.append(f"เอกสารใกล้เคียงที่ระบบค้นเจอ (ยังไม่มีคำตอบตรงคำถาม):\n{listed}")

    tips = _suggestions(question, rf)
    if tips:
        listed_tips = "\n".join(f"- {tip}" for tip in tips)
        parts.append(f"คำแนะนำในการค้นหา:\n{listed_tips}")

    if re.search(r"(เครื่อง|machine|mc-\d+|alarm|error|ซ่อม|manual|drawing|terminal)", question or "", re.IGNORECASE):
        parts.append("หากยังไม่พบ กรุณาติดต่อวิศวกรหรือผู้ดูแลเอกสารครับ")
    else:
        parts.append("หากยังไม่พบ กรุณาติดต่อผู้ดูแลเอกสารหรือทีมที่รับผิดชอบหัวข้อนี้ครับ")
    return "\n\n".join(parts)
