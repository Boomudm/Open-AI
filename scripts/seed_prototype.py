#!/usr/bin/env python3
"""Seed a small, repeatable factory demo for local product prototyping.

The script is idempotent: running it again updates the same demo records instead
of creating duplicates. It never deletes user-created data.
"""
from __future__ import annotations

import asyncio
import hashlib
import io
import sys
import uuid
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from sqlalchemy import select

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from spark.core.auth import hash_password
from spark.core.database import AsyncSessionLocal
from spark.core.privacy_policy import PRIVACY_POLICY_VERSION
from spark.db.models.chat import ChatMessage, ChatSession
from spark.db.models.docs import Document
from spark.db.models.feedback import KnowledgeFeedback
from spark.db.models.job_positions import JobPosition, UserJobPosition
from spark.db.models.org import (
    Component,
    Factory,
    Machine,
    MachineAlias,
    Role,
    User,
    UserFactoryAccess,
    UserRole,
)
from spark.storage import get_storage

FACTORY_ID = "F-01"
DEMO_PASSWORD = "Demo1234!"
NS = uuid.UUID("f30acdbe-b465-49af-8f38-bd5e62755c74")


def stable_uuid(kind: str, key: str) -> uuid.UUID:
    return uuid.uuid5(NS, f"{kind}:{key}")


def pdf_bytes(title: str, sections: list[tuple[str, list[str]]]) -> bytes:
    output = io.BytesIO()
    pdf = canvas.Canvas(output, pagesize=A4, pageCompression=1)
    width, height = A4
    pdf.setFillColor(HexColor("#07111f"))
    pdf.rect(0, 0, width, height, fill=1, stroke=0)
    pdf.setFillColor(HexColor("#38bdf8"))
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(48, height - 48, "SPARK OPS  /  LOCAL PROTOTYPE")
    pdf.setFillColor(HexColor("#f8fafc"))
    pdf.setFont("Helvetica-Bold", 23)
    pdf.drawString(48, height - 92, title)
    y = height - 138
    for heading, lines in sections:
        if y < 120:
            pdf.showPage()
            y = height - 60
        pdf.setFillColor(HexColor("#22c55e"))
        pdf.setFont("Helvetica-Bold", 13)
        pdf.drawString(48, y, heading)
        y -= 24
        pdf.setFillColor(HexColor("#dbeafe"))
        pdf.setFont("Helvetica", 10)
        for line in lines:
            pdf.drawString(62, y, f"- {line}")
            y -= 18
        y -= 12
    pdf.setFillColor(HexColor("#64748b"))
    pdf.setFont("Helvetica", 8)
    pdf.drawString(48, 32, "Demo document generated locally. Replace with approved plant documentation.")
    pdf.save()
    return output.getvalue()


async def get_or_create(session, model, key, **values):
    row = await session.get(model, key)
    if row is None:
        row = model(**values)
        session.add(row)
    else:
        for field, value in values.items():
            if field not in {"user_id", "role_id", "factory_id", "position_id"}:
                setattr(row, field, value)
    return row


async def seed() -> None:
    now = datetime.now(UTC)
    async with AsyncSessionLocal() as session:
        factory = await session.get(Factory, FACTORY_ID)
        if factory is None:
            factory = Factory(factory_id=FACTORY_ID, factory_name="Spark Demo Plant")
            session.add(factory)
        factory.factory_name = "Spark Demo Plant"
        factory.location = "Eastern Economic Corridor, Thailand"

        roles = {
            row.role_code: row
            for row in (await session.execute(select(Role))).scalars().all()
        }

        positions_spec = [
            ("maintenance", "ช่างซ่อมบำรุง", 10),
            ("production", "หัวหน้าฝ่ายผลิต", 20),
            ("quality", "วิศวกรคุณภาพ", 30),
            ("safety", "เจ้าหน้าที่ความปลอดภัย", 40),
        ]
        positions: dict[str, JobPosition] = {}
        for code, name, order in positions_spec:
            row = await session.scalar(select(JobPosition).where(JobPosition.position_code == code))
            if row is None:
                row = JobPosition(position_code=code, name_th=name)
                session.add(row)
                await session.flush()
            row.name_th = name
            row.description = "ข้อมูลตัวอย่างสำหรับต้นแบบ Spark Ops"
            row.sort_order = order
            row.is_active = True
            positions[code] = row

        user_specs = [
            ("operator", "สมชาย ใจดี", "operator@spark.local", "operator", "production", "write"),
            ("engineer", "พิมพ์ชนก วิศวกร", "engineer@spark.local", "employee", "maintenance", "write"),
            ("viewer", "กิตติ พนักงานไลน์", "viewer@spark.local", "employee", "quality", "read"),
        ]
        users: dict[str, User] = {}
        for username, full_name, email, role_code, position_code, access in user_specs:
            user = await session.scalar(select(User).where(User.username == username))
            if user is None:
                user = User(
                    user_id=stable_uuid("user", username),
                    username=username,
                    password_hash=hash_password(DEMO_PASSWORD),
                )
                session.add(user)
            user.full_name = full_name
            user.email = email
            user.is_active = True
            user.privacy_policy_accepted_at = now
            user.privacy_policy_version = PRIVACY_POLICY_VERSION
            await session.flush()
            if role_code in roles and await session.get(UserRole, (user.user_id, roles[role_code].role_id)) is None:
                session.add(UserRole(user_id=user.user_id, role_id=roles[role_code].role_id))
            access_row = await session.get(UserFactoryAccess, (user.user_id, FACTORY_ID))
            if access_row is None:
                session.add(UserFactoryAccess(user_id=user.user_id, factory_id=FACTORY_ID, access_level=access))
            else:
                access_row.access_level = access
            if await session.get(UserJobPosition, (user.user_id, positions[position_code].position_id)) is None:
                session.add(UserJobPosition(user_id=user.user_id, position_id=positions[position_code].position_id))
            users[username] = user

        admin = await session.scalar(select(User).where(User.username == "admin"))
        if admin and await session.get(UserJobPosition, (admin.user_id, positions["maintenance"].position_id)) is None:
            session.add(UserJobPosition(user_id=admin.user_id, position_id=positions["maintenance"].position_id))

        machine_specs = [
            ("MIX-01", "Main Mixing Tank", "Mixer", "Tetra Pak", "M-500", date(2022, 3, 15), "Critical line asset · PM every 500 hours"),
            ("FILL-01", "Aseptic Filling Line", "Filler", "Krones", "AF-240", date(2021, 8, 2), "Line 1 · target OEE 85%"),
            ("PACK-01", "Carton Packing Cell", "Packaging", "ABB", "IRB-460", date(2023, 1, 20), "Robot cell · safety zone A"),
            ("CHILL-01", "Process Chiller", "Utility", "Daikin", "UW-90", date(2020, 11, 9), "Supplies chilled water to production"),
            ("AIR-01", "Main Air Compressor", "Utility", "Atlas Copco", "GA-75", date(2019, 6, 12), "7.2 bar plant air header"),
            ("CIP-01", "CIP Skid", "Cleaning", "Alfa Laval", "CIP-3", date(2022, 9, 1), "Three-tank clean-in-place system"),
        ]
        machines: dict[str, Machine] = {}
        for machine_id, name, kind, maker, model, installed, notes in machine_specs:
            machine = await get_or_create(
                session, Machine, machine_id, machine_id=machine_id, factory_id=FACTORY_ID,
                machine_name=name, machine_type=kind, manufacturer=maker,
                model_number=model, install_date=installed, notes=notes, is_active=True,
            )
            machines[machine_id] = machine
        await session.flush()

        alias_specs = [("MIX-01", "ถังผสมหลัก"), ("FILL-01", "เครื่องบรรจุไลน์ 1"), ("AIR-01", "ปั๊มลมใหญ่")]
        for machine_id, alias in alias_specs:
            exists = await session.scalar(select(MachineAlias).where(MachineAlias.machine_id == machine_id, MachineAlias.alias == alias))
            if exists is None:
                session.add(MachineAlias(machine_id=machine_id, alias=alias, source="prototype"))

        component_specs = [
            ("MIX-01-MOTOR", "MIX-01", "Agitator Motor", "Motor", "ABB", "M3BP-160"),
            ("MIX-01-SEAL", "MIX-01", "Mechanical Seal", "Seal", "EagleBurgmann", "M7N"),
            ("FILL-01-PUMP", "FILL-01", "Product Pump", "Pump", "Alfa Laval", "LKH-25"),
            ("AIR-01-FILTER", "AIR-01", "Oil Separator", "Filter", "Atlas Copco", "1622-0646"),
        ]
        for cid, mid, name, kind, maker, part in component_specs:
            await get_or_create(
                session, Component, cid, component_id=cid, machine_id=mid,
                component_name=name, component_type=kind, manufacturer=maker,
                part_number=part, depth=0, is_active=True,
            )

        docs_spec = [
            ("mixing-sop", "MIX-01", "SOP การเดินเครื่องถังผสม", "knowledge", "sop", "R03", [
                ("Pre-start checks", ["Verify guard and emergency stop", "Confirm product valve alignment", "Record batch number"]),
                ("Normal operation", ["Start agitator at low speed", "Increase to recipe setpoint", "Monitor motor current below 28 A"]),
                ("Abnormal condition", ["Stop on seal leakage", "Isolate energy before inspection", "Notify shift supervisor"]),
            ]),
            ("filler-maintenance", "FILL-01", "คู่มือบำรุงรักษาเครื่องบรรจุ", "knowledge", "machine_manual", "R05", [
                ("Daily inspection", ["Check product pressure", "Inspect nozzle seals", "Clean photoelectric sensors"]),
                ("Weekly service", ["Lubricate star-wheel bearings", "Verify reject station", "Back up recipe parameters"]),
            ]),
            ("compressor-troubleshoot", "AIR-01", "แนวทางแก้ปัญหาแรงดันลมตก", "knowledge", "machine_manual", "R02", [
                ("Low pressure", ["Check header for leakage", "Inspect inlet filter differential pressure", "Confirm unload solenoid operation"]),
                ("Escalation", ["Stop above 105 C discharge temperature", "Use lockout-tagout before opening panels"]),
            ]),
            ("cip-safety", "CIP-01", "ข้อกำหนดความปลอดภัยระบบ CIP", "knowledge", "sop", "R04", [
                ("PPE", ["Chemical goggles and face shield", "Alkali-resistant gloves", "Safety footwear"]),
                ("Chemical exposure", ["Use emergency shower for 15 minutes", "Call plant emergency number", "Bring SDS to clinic"]),
            ]),
            ("quality-hold", None, "ขั้นตอนกักกันผลิตภัณฑ์ไม่เป็นไปตามข้อกำหนด", "enterprise", "company_policy", "R01", [
                ("Containment", ["Stop affected lot", "Attach HOLD label", "Move material to quarantine area"]),
                ("Disposition", ["Quality manager reviews evidence", "Record release or scrap decision"]),
            ]),
        ]
        docs: dict[str, Document] = {}
        storage = get_storage()
        for key, machine_id, title, category, doc_type, revision, sections in docs_spec:
            doc_id = stable_uuid("document", key)
            payload = pdf_bytes(title, sections)
            filename = f"{key}.pdf"
            uri = await storage.save_document(
                doc_id, filename, io.BytesIO(payload), factory_id=FACTORY_ID,
                document_type=doc_type, machine_id=machine_id, content_type="application/pdf",
            )
            doc = await get_or_create(
                session, Document, doc_id, doc_id=doc_id, factory_id=FACTORY_ID,
                machine_id=machine_id, document_category=category, document_type=doc_type,
                title=title, language="th", revision=revision, effective_date=date(2026, 1, 1),
                source_file=filename, original_filename=filename, mime_type="application/pdf",
                storage_uri=uri, file_hash_sha256=hashlib.sha256(payload).hexdigest(),
                file_size_bytes=len(payload), page_count=1, ingest_status="completed",
                chunks_count=sum(len(lines) for _, lines in sections), retrieval_enabled=True,
                extra_metadata={"prototype_seed": True, "approved": True}, created_by=admin.user_id if admin else None,
            )
            docs[key] = doc

        owner = admin or users["operator"]
        chats = [
            ("morning-check", "ตรวจเช็กก่อนเริ่มไลน์ผลิต", True, "ก่อนเริ่มเครื่อง MIX-01 ต้องตรวจอะไรบ้าง?", "ตรวจ guard และ emergency stop, ยืนยันตำแหน่งวาล์วผลิตภัณฑ์ และบันทึกหมายเลข batch ก่อนเริ่ม agitator ครับ", "mixing-sop"),
            ("air-pressure", "วิเคราะห์แรงดันลมตก", False, "แรงดันลมที่ header ตก ควรเริ่มเช็กจากจุดไหน?", "เริ่มจากสำรวจการรั่วที่ header จากนั้นตรวจ differential pressure ของ inlet filter และการทำงานของ unload solenoid ครับ", "compressor-troubleshoot"),
            ("cip-ppe", "PPE สำหรับงาน CIP", False, "เข้าเขต CIP ต้องใส่ PPE อะไร?", "ควรใช้แว่นครอบตาและ face shield, ถุงมือทนด่าง และรองเท้านิรภัย ตามเอกสารความปลอดภัยระบบ CIP ครับ", "cip-safety"),
        ]
        chat_rows: dict[str, tuple[ChatSession, ChatMessage]] = {}
        for idx, (key, title, pinned, question, answer, doc_key) in enumerate(chats):
            sid = stable_uuid("chat", key)
            chat = await get_or_create(
                session, ChatSession, sid, session_id=sid, user_id=owner.user_id,
                title=title, pinned=pinned, pinned_at=now - timedelta(days=idx) if pinned else None,
                context={"factory_id": FACTORY_ID, "prototype_seed": True},
            )
            user_mid = stable_uuid("message-user", key)
            answer_mid = stable_uuid("message-assistant", key)
            await get_or_create(session, ChatMessage, user_mid, message_id=user_mid, session_id=sid, role="user", content=question)
            source_doc = docs[doc_key]
            reply = await get_or_create(
                session, ChatMessage, answer_mid, message_id=answer_mid, session_id=sid,
                role="assistant", content=answer,
                sources=[{"doc_id": str(source_doc.doc_id), "title": source_doc.title, "source_file": source_doc.source_file, "page": 1}],
                confidence_tier="high", cache_hit=False, verified_at=now,
            )
            chat_rows[key] = (chat, reply)

        feedback_specs = [
            ("missing-torque", "MIX-01", "mixing-sop", "missing_step", "คู่มือยังไม่มีค่า torque สำหรับฝาครอบ coupling", "open"),
            ("old-photo", "FILL-01", "filler-maintenance", "outdated", "รูปตำแหน่ง sensor เป็นรุ่นเก่า ไม่ตรงกับเครื่องปัจจุบัน", "triaged"),
            ("clear-ppe", "CIP-01", "cip-safety", "unclear", "ควรระบุชนิดถุงมือและเวลาที่ต้องเปลี่ยนให้ชัดเจน", "resolved"),
        ]
        for key, machine_id, doc_key, issue, comment, status in feedback_specs:
            fid = stable_uuid("feedback", key)
            resolved = status == "resolved"
            await get_or_create(
                session, KnowledgeFeedback, fid, feedback_id=fid, factory_id=FACTORY_ID,
                machine_id=machine_id, source_type="document", doc_id=docs[doc_key].doc_id,
                page=1, comment=comment, issue_type=issue, status=status,
                context={"prototype_seed": True, "document_title": docs[doc_key].title},
                resolution_note="ปรับข้อความใน revision ถัดไปแล้ว" if resolved else None,
                resolved_by=admin.user_id if resolved and admin else None,
                resolved_at=now - timedelta(days=1) if resolved else None,
                created_by=users["operator"].user_id,
            )

        await session.commit()

    print("Prototype data ready")
    print(f"Factory: {FACTORY_ID} / Spark Demo Plant")
    print(f"Demo users: operator, engineer, viewer / password: {DEMO_PASSWORD}")
    print("Seeded: 4 job positions, 6 machines, 4 components, 5 PDFs, 3 chats, 3 feedback items")


if __name__ == "__main__":
    asyncio.run(seed())
