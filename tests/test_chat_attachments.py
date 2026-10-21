"""Chat attachment upload and extract tests."""

from __future__ import annotations

import io

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient

from spark.core.config import settings
from spark.main import app
from spark.schemas.rag import AskResponse
from spark.services.chat_attachment_service import (
    AttachmentExtractError,
    PreparedAttachment,
    resolve_attachment_mime,
    validate_attachment_uploads,
)
from spark.storage import get_storage


@pytest.fixture(autouse=True)
def _demo_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "auth_required", False)


@pytest.fixture
def storage_dirs(tmp_path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "documents_dir", tmp_path / "documents")
    monkeypatch.setattr(settings, "machines_dir", tmp_path / "machines")
    monkeypatch.setattr(settings, "feedback_dir", tmp_path / "feedback")
    monkeypatch.setattr(settings, "chat_attachments_dir", tmp_path / "chat")
    get_storage.cache_clear()
    yield tmp_path
    get_storage.cache_clear()


def test_resolve_attachment_mime_pdf() -> None:
    assert resolve_attachment_mime("alarm.pdf", "application/pdf") == "application/pdf"


def test_resolve_attachment_mime_rejects_docx() -> None:
    assert resolve_attachment_mime("notes.docx", None) is None


@pytest.mark.asyncio
async def test_multipart_rejects_unsupported_mime(storage_dirs) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        session = (await client.post("/api/v1/chat/sessions", json={})).json()
        files = {"files": ("notes.docx", io.BytesIO(b"hello"), "application/msword")}
        data = {"question": "summarize this", "filter_json": '{"factory_id":"F-01"}'}
        res = await client.post(
            f"/api/v1/chat/{session['session_id']}/ask",
            data=data,
            files=files,
        )
        assert res.status_code == 422


@pytest.mark.asyncio
async def test_multipart_rejects_invalid_filter_json(storage_dirs) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        session = (await client.post("/api/v1/chat/sessions", json={})).json()
        files = {"files": ("panel.png", io.BytesIO(b"\x89PNG\r\n"), "image/png")}
        data = {"question": "what is this", "filter_json": "{not-json"}
        res = await client.post(
            f"/api/v1/chat/{session['session_id']}/ask",
            data=data,
            files=files,
        )
        assert res.status_code == 422
        assert "invalid filter_json" in res.json()["detail"]


@pytest.mark.asyncio
async def test_extract_failure_cleans_up_storage(
    storage_dirs,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_extract(uri: str, filename: str, mime: str) -> str:
        raise AttachmentExtractError(filename, "OCR returned no text")

    monkeypatch.setattr(
        "spark.services.chat_attachment_service.extract_attachment_text",
        fake_extract,
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        session = (await client.post("/api/v1/chat/sessions", json={})).json()
        session_id = session["session_id"]
        files = {"files": ("panel.png", io.BytesIO(b"\x89PNG\r\n"), "image/png")}
        data = {"question": "what is this", "filter_json": '{"factory_id":"F-01"}'}
        res = await client.post(
            f"/api/v1/chat/{session_id}/ask",
            data=data,
            files=files,
        )
        assert res.status_code == 422
        assert "cannot read attachment" in res.json()["detail"]

        messages = (await client.get(f"/api/v1/chat/{session_id}/messages")).json()["items"]
        assert messages == []

        chat_dir = storage_dirs / "chat"
        if chat_dir.exists():
            assert not any(path.is_file() for path in chat_dir.rglob("*"))


@pytest.mark.asyncio
async def test_multipart_ask_persists_attachment_metadata(
    storage_dirs,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = [
        PreparedAttachment(
            filename="panel.png",
            mime_type="image/png",
            file_size_bytes=8,
            storage_uri="file:///tmp/panel.png",
            extracted_text="alarm code E42",
            sort_order=0,
        )
    ]

    async def fake_prepare(**kwargs):
        return prepared, [prepared[0].storage_uri]

    async def fake_ask(session_obj, req, db, **kwargs):
        await db.commit()
        return AskResponse(
            answer="E42 means servo overheat",
            sources=[],
            used_filters={},
            intent="factual",
            fallback_level=0,
        )

    monkeypatch.setattr("spark.api.v1.endpoints.chat.prepare_attachments", fake_prepare)
    monkeypatch.setattr(
        "spark.services.chat_orchestrator.chat_orchestrator.ask",
        fake_ask,
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        session = (await client.post("/api/v1/chat/sessions", json={})).json()
        session_id = session["session_id"]
        files = {"files": ("panel.png", io.BytesIO(b"\x89PNG\r\n"), "image/png")}
        data = {"question": "what alarm is this", "filter_json": '{"factory_id":"F-01"}'}
        res = await client.post(
            f"/api/v1/chat/{session_id}/ask",
            data=data,
            files=files,
        )
        assert res.status_code == 200

        messages = (await client.get(f"/api/v1/chat/{session_id}/messages")).json()["items"]
        user_messages = [m for m in messages if m["role"] == "user"]
        assert user_messages
        attachments = user_messages[-1]["attachments"]
        assert len(attachments) == 1
        assert attachments[0]["filename"] == "panel.png"
        assert attachments[0]["mime_type"] == "image/png"
        assert f"/attachments/{attachments[0]['sort_order']}" in attachments[0]["url"]


def test_validate_attachment_uploads_too_many() -> None:
    class FakeUpload:
        filename = "a.png"

        async def read(self):
            return b"x"

    uploads = [FakeUpload() for _ in range(settings.max_chat_attachments_per_message + 1)]
    with pytest.raises(HTTPException) as exc:
        validate_attachment_uploads(uploads)  # type: ignore[arg-type]
    assert exc.value.status_code == 422
