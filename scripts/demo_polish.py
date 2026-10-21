"""Optional demo polish — sample chat sessions + feedback for dashboard widgets."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select

from spark.core.database import AsyncSessionLocal
from spark.db.models.chat import ChatMessage, ChatSession
from spark.db.models.feedback import KnowledgeFeedback
from spark.db.models.insights import QuestionAnalytics
from spark.db.models.org import User
from spark.services.topic_extractor import extract_topic

NS = uuid.NAMESPACE_DNS
POLISH_SESSION_ID = uuid.uuid5(NS, "demo-polish-session-mc001")
POLISH_SESSION2_ID = uuid.uuid5(NS, "demo-polish-session-mc002")

SAMPLE_QA: list[tuple[str, str, str, str, int]] = [
    # session_id_key, machine_id, factory_id, question, days_ago
    ("mc001", "MC-001", "F-01", "MC-001 ร้อนผิดปกติ ต้องทำอะไร", 3),
    ("mc001", "MC-001", "F-01", "ลูกปืน 6205-2RS เปลี่ยนยังไง", 2),
    ("mc002", "MC-002", "F-01", "MC-002 hydraulic มี vibration สูง ตรวจอะไร", 4),
]

ASSISTANT_SNIPPETS: dict[str, str] = {
    "MC-001 ร้อนผิดปกติ ต้องทำอะไร": (
        "ตรวจพัดลมระบายความร้อน ลูกปืน 6205-2RS และ encoder cable "
        "ตามคู่มือ MC-001 §4.2 — หยุดเครื่องก่อนตรวจ"
    ),
    "ลูกปืน 6205-2RS เปลี่ยนยังไง": (
        "ถอดฝาครอบ คลายสกรูยึด bearing housing แล้วดึงลูกปืนเดิม "
        "ใส่ 6205-2RS ใหม่ พร้อม grease ตาม spec"
    ),
    "MC-002 hydraulic มี vibration สูง ตรวจอะไร": (
        "ตรวจ anchor bolt แรงดันน้ำมัน hydraulic และ filter — "
        "อ้างอิงคู่มือ MC-002 §3.1"
    ),
}

FEEDBACK_SAMPLES: list[tuple[str, str, str, str, int]] = [
    # factory, machine, issue_type, comment, days_ago
    ("F-01", "MC-001", "outdated", "คู่มือ §4.2 ยังไม่ระบุ torque ลูกปืน 6205", 5),
    ("F-01", "MC-002", "missing", "ไม่มีขั้นตอน bleed hydraulic หลังเปลี่ยน seal", 8),
    ("F-02", "MC-009", "unclear", "SOP กะเช้า ไม่ชัดเรื่อง lockout ก่อนซ่อม", 12),
]


async def _admin_user(session) -> User | None:
    return await session.scalar(select(User).where(User.username == "admin"))


async def seed_demo_polish() -> dict[str, int]:
    """Idempotent polish rows for AI trends, problem pulse, and feedback gaps."""
    now = datetime.now(tz=timezone.utc)
    stats = {"sessions": 0, "messages": 0, "analytics": 0, "feedback": 0}

    async with AsyncSessionLocal() as session:
        admin = await _admin_user(session)
        admin_id = admin.user_id if admin else None

        session_ids = {
            "mc001": POLISH_SESSION_ID,
            "mc002": POLISH_SESSION2_ID,
        }

        for key, sid in session_ids.items():
            existing = await session.get(ChatSession, sid)
            if existing is None:
                title = "MC-001 overheating" if key == "mc001" else "MC-002 hydraulic"
                session.add(
                    ChatSession(
                        session_id=sid,
                        user_id=admin_id,
                        title=title,
                        context={"factory_id": "F-01"},
                    )
                )
                stats["sessions"] += 1

        for key, machine_id, factory_id, question, days_ago in SAMPLE_QA:
            sid = session_ids["mc001" if machine_id == "MC-001" else "mc002"]
            asked_at = now - timedelta(days=days_ago)
            user_msg_id = uuid.uuid5(NS, f"demo-polish-user-{question[:40]}")
            asst_msg_id = uuid.uuid5(NS, f"demo-polish-asst-{question[:40]}")

            if await session.get(ChatMessage, user_msg_id) is None:
                session.add(
                    ChatMessage(
                        message_id=user_msg_id,
                        session_id=sid,
                        role="user",
                        content=question,
                        created_at=asked_at,
                    )
                )
                stats["messages"] += 1

            answer = ASSISTANT_SNIPPETS.get(question, "ดูคู่มือเครื่องและ SOP ที่เกี่ยวข้อง")
            if await session.get(ChatMessage, asst_msg_id) is None:
                session.add(
                    ChatMessage(
                        message_id=asst_msg_id,
                        session_id=sid,
                        role="assistant",
                        content=answer,
                        sources=[{"machine_id": machine_id, "document_type": "machine_manual"}],
                        created_at=asked_at + timedelta(seconds=30),
                    )
                )
                stats["messages"] += 1

            if await session.get(QuestionAnalytics, uuid.uuid5(NS, f"qa-{user_msg_id}")) is None:
                topic = extract_topic(question)
                session.add(
                    QuestionAnalytics(
                        analytics_id=uuid.uuid5(NS, f"qa-{user_msg_id}"),
                        message_id=user_msg_id,
                        factory_id=factory_id,
                        machine_id=machine_id,
                        intent="rag",
                        topic_label=topic.topic_label,
                        topic_confidence=topic.topic_confidence,
                        topic_source="heuristic",
                        asked_at=asked_at,
                    )
                )
                stats["analytics"] += 1

        for factory_id, machine_id, issue_type, comment, days_ago in FEEDBACK_SAMPLES:
            fid = uuid.uuid5(NS, f"demo-polish-fb-{factory_id}-{issue_type}-{machine_id}")
            if await session.get(KnowledgeFeedback, fid) is not None:
                continue
            created_at = now - timedelta(days=days_ago)
            session.add(
                KnowledgeFeedback(
                    feedback_id=fid,
                    factory_id=factory_id,
                    machine_id=machine_id,
                    source_type="chat",
                    comment=comment,
                    issue_type=issue_type,
                    status="resolved",
                    resolution_note="อัปเดตเอกสารในรอบ PM ถัดไป",
                    resolved_by=admin_id,
                    resolved_at=created_at + timedelta(days=1),
                    created_by=admin_id,
                    created_at=created_at,
                )
            )
            stats["feedback"] += 1

        await session.commit()

    print(
        "demo_polish: "
        f"{stats['sessions']} sessions, {stats['messages']} messages, "
        f"{stats['analytics']} analytics, {stats['feedback']} feedback"
    )
    return stats


async def reset_demo_polish() -> None:
    """Remove polish rows (for full reset flows)."""
    async with AsyncSessionLocal() as session:
        msg_ids = [
            uuid.uuid5(NS, f"demo-polish-user-{q[:40]}")
            for _, _, _, q, _ in SAMPLE_QA
        ]
        await session.execute(delete(QuestionAnalytics).where(QuestionAnalytics.message_id.in_(msg_ids)))
        await session.execute(
            delete(ChatMessage).where(
                ChatMessage.session_id.in_([POLISH_SESSION_ID, POLISH_SESSION2_ID])
            )
        )
        await session.execute(delete(ChatSession).where(ChatSession.session_id.in_([POLISH_SESSION_ID, POLISH_SESSION2_ID])))
        fb_ids = [
            uuid.uuid5(NS, f"demo-polish-fb-{f}-{it}-{m}")
            for f, m, it, _, _ in FEEDBACK_SAMPLES
        ]
        await session.execute(delete(KnowledgeFeedback).where(KnowledgeFeedback.feedback_id.in_(fb_ids)))
        await session.commit()
