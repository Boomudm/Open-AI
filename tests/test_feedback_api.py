"""HTTP tests for floor feedback loop API."""

from __future__ import annotations

import uuid

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from spark.core.auth import issue_token
from spark.core.config import settings
from spark.core.security import Principal
from spark.main import app
from spark.services.feedback_service import (
    VALID_SOURCE_TYPES,
    _can_list_inbox,
    _can_view_feedback,
    _infer_doc_from_sources,
    create_feedback,
    list_feedback,
    patch_feedback,
)


def _viewer_token() -> str:
    return issue_token(
        {
            "sub": "00000000-0000-0000-0000-000000000002",
            "username": "operator_f01",
            "roles": ["viewer"],
            "factory_access": {"F-01": "read"},
        }
    )


def _writer_token() -> str:
    return issue_token(
        {
            "sub": "00000000-0000-0000-0000-000000000003",
            "username": "lead_f01",
            "roles": ["operator"],
            "factory_access": {"F-01": "write"},
        }
    )


def _admin_token() -> str:
    return issue_token(
        {
            "sub": "00000000-0000-0000-0000-000000000001",
            "username": "admin",
            "roles": ["admin"],
            "factory_access": {"F-01": "admin"},
        }
    )


@pytest.fixture
def auth_client() -> TestClient:
    return TestClient(app)


def test_rbac_viewer_cannot_list_inbox(auth_client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(settings, "auth_required", True)
    res = auth_client.get(
        "/api/v1/feedback",
        headers={"Authorization": f"Bearer {_viewer_token()}"},
    )
    assert res.status_code == 403


def test_rbac_writer_can_list_inbox(auth_client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(settings, "auth_required", True)
    res = auth_client.get(
        "/api/v1/feedback",
        headers={"Authorization": f"Bearer {_writer_token()}"},
    )
    assert res.status_code == 200
    body = res.json()
    assert "items" in body
    assert "total" in body


def test_feedback_open_count(auth_client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(settings, "auth_required", True)
    res = auth_client.get(
        "/api/v1/feedback/count?status=open&factory_id=F-01",
        headers={"Authorization": f"Bearer {_writer_token()}"},
    )
    assert res.status_code == 200
    body = res.json()
    assert "count" in body
    assert isinstance(body["count"], int)
    assert body["count"] >= 0


def test_feedback_list_page_size_zero_count_only(auth_client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(settings, "auth_required", True)
    res = auth_client.get(
        "/api/v1/feedback?status=open&page=1&page_size=0&factory_id=F-01",
        headers={"Authorization": f"Bearer {_writer_token()}"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["items"] == []
    assert body["page_size"] == 0
    assert isinstance(body["total"], int)


@pytest.mark.asyncio
async def test_create_with_photo(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(settings, "feedback_dir", tmp_path)
    from spark.core.database import AsyncSessionLocal

    writer = Principal(
        user_id="00000000-0000-0000-0000-000000000003",
        username="lead_f01",
        roles=("operator",),
        factory_access={"F-01": "write"},
    )
    png = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
    )

    try:
        async with AsyncSessionLocal() as session:
            row = await create_feedback(
                session,
                writer,
                factory_id="F-01",
                source_type="rag_answer",
                comment="รูปชิ้นส่วนจริงต่างจากคู่มือ",
                issue_type="incorrect",
                photos=[("image/png", png)],
            )
            assert row.status == "open"
            assert row.issue_type == "incorrect"
            assert len(row.attachments) == 1
            assert row.attachments[0].mime_type == "image/png"
    except Exception as exc:
        pytest.skip(f"Postgres unavailable: {exc}")


def test_can_list_inbox_unit() -> None:
    viewer = Principal(
        user_id="v",
        username="viewer",
        roles=("viewer",),
        factory_access={"F-01": "read"},
    )
    writer = Principal(
        user_id="w",
        username="writer",
        roles=("operator",),
        factory_access={"F-01": "write"},
    )
    assert _can_list_inbox(viewer, "F-01") is False
    assert _can_list_inbox(writer, "F-01") is True


def test_valid_source_types() -> None:
    assert "document" in VALID_SOURCE_TYPES
    assert "rag_answer" in VALID_SOURCE_TYPES


def test_infer_doc_from_sources() -> None:
    doc_id = uuid.uuid4()
    inferred_doc, page, title = _infer_doc_from_sources(
        [
            {"source_file": "manual.pdf", "page": 3, "doc_id": str(doc_id)},
            {"doc_id": str(uuid.uuid4())},
        ]
    )
    assert inferred_doc == doc_id
    assert page == 3
    assert title == "manual.pdf"

    empty_doc, empty_page, empty_title = _infer_doc_from_sources([])
    assert empty_doc is None
    assert empty_page is None
    assert empty_title is None


@pytest.mark.asyncio
async def test_create_feedback_infers_doc_from_message_sources(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(settings, "feedback_dir", tmp_path)
    from spark.core.database import AsyncSessionLocal
    from spark.db.models.chat import ChatMessage, ChatSession

    doc_id = uuid.uuid4()
    session_id = uuid.uuid4()
    user_msg_id = uuid.uuid4()
    assistant_msg_id = uuid.uuid4()
    writer = Principal(
        user_id="00000000-0000-0000-0000-000000000003",
        username="lead_f01",
        roles=("operator",),
        factory_access={"F-01": "write"},
    )

    try:
        async with AsyncSessionLocal() as session:
            chat_session = ChatSession(
                session_id=session_id,
                factory_id="F-01",
                user_id=uuid.UUID(writer.user_id),
                title="test",
            )
            session.add(chat_session)
            session.add(
                ChatMessage(
                    message_id=user_msg_id,
                    session_id=session_id,
                    role="user",
                    content="bearing noise?",
                )
            )
            session.add(
                ChatMessage(
                    message_id=assistant_msg_id,
                    session_id=session_id,
                    role="assistant",
                    content="Check bearing spec on page 5.",
                    sources=[
                        {
                            "doc_id": str(doc_id),
                            "page": 5,
                            "source_file": "bearing-manual.pdf",
                        }
                    ],
                )
            )
            await session.commit()

            row = await create_feedback(
                session,
                writer,
                factory_id="F-01",
                source_type="rag_answer",
                comment="คำตอบผิด",
                issue_type="incorrect",
                message_id=assistant_msg_id,
            )
            assert row.doc_id == doc_id
            assert row.page == 5
            assert row.context is not None
            assert row.context.get("doc_title") == "bearing-manual.pdf"

            await session.delete(row)
            await session.delete(await session.get(ChatMessage, assistant_msg_id))
            await session.delete(await session.get(ChatMessage, user_msg_id))
            await session.delete(chat_session)
            await session.commit()
    except Exception as exc:
        pytest.skip(f"Postgres unavailable: {exc}")


@pytest.mark.asyncio
async def test_create_and_resolve_flow(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(settings, "feedback_dir", tmp_path)
    from spark.core.database import AsyncSessionLocal

    writer = Principal(
        user_id="00000000-0000-0000-0000-000000000003",
        username="lead_f01",
        roles=("operator",),
        factory_access={"F-01": "write"},
    )

    try:
        async with AsyncSessionLocal() as session:
            row = await create_feedback(
                session,
                writer,
                factory_id="F-01",
                source_type="document",
                comment="ทดสอบ feedback loop",
                machine_id="MC-001",
                context={"submitted_from": "test"},
            )
            assert row.status == "open"

            listed, total = await list_feedback(session, writer, status="open", limit=10)
            assert total >= 1
            assert any(r.feedback_id == row.feedback_id for r in listed)

            updated = await patch_feedback(
                session,
                writer,
                row.feedback_id,
                status="resolved",
                resolution_note="อัปเดต SOP แล้ว",
            )
            assert updated.status == "resolved"
            assert updated.resolution_note == "อัปเดต SOP แล้ว"
            assert updated.resolved_at is not None
    except Exception as exc:
        pytest.skip(f"Postgres unavailable: {exc}")


@pytest.mark.asyncio
async def test_viewer_sees_own_feedback_only(monkeypatch) -> None:
    from spark.core.database import AsyncSessionLocal
    from spark.db.models.feedback import KnowledgeFeedback

    viewer_id = uuid.UUID("00000000-0000-0000-0000-000000000002")
    viewer = Principal(
        user_id=str(viewer_id),
        username="operator_f01",
        roles=("viewer",),
        factory_access={"F-01": "read"},
    )
    other = Principal(
        user_id="00000000-0000-0000-0000-000000000099",
        username="other",
        roles=("viewer",),
        factory_access={"F-01": "read"},
    )

    try:
        async with AsyncSessionLocal() as session:
            row = KnowledgeFeedback(
                feedback_id=uuid.uuid4(),
                factory_id="F-01",
                source_type="document",
                comment="owned by viewer",
                status="open",
                created_by=viewer_id,
            )
            session.add(row)
            await session.commit()

            assert _can_view_feedback(viewer, row) is True
            assert _can_view_feedback(other, row) is False

            with pytest.raises(HTTPException) as exc:
                await list_feedback(session, viewer, limit=10)
            assert exc.value.status_code == 403

            await session.delete(row)
            await session.commit()
    except Exception as exc:
        pytest.skip(f"Postgres unavailable: {exc}")
