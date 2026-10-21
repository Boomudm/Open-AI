"""Secure document file endpoint tests."""

from __future__ import annotations

import io
import uuid
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from spark.core.auth import issue_token
from spark.core.config import settings
from spark.core.security import Principal
from spark.main import app
from spark.services.document_access_service import _passes_factory_acl
from spark.storage.local import LocalStorageBackend


def _operator_token() -> str:
    return issue_token(
        {
            "sub": "00000000-0000-0000-0000-000000000002",
            "username": "operator_f01",
            "roles": ["employee"],
            "factory_access": {"F-01": "read"},
            "token_version": 0,
        }
    )


def test_can_access_blocks_foreign_factory() -> None:
    p = Principal(
        user_id="u",
        username="viewer",
        roles=("employee",),
        factory_access={"F-01": "read"},
    )

    class Doc:
        factory_id = "F-02"
        doc_id = uuid.uuid4()

    assert _passes_factory_acl(p, Doc()) is False


@pytest.mark.asyncio
async def test_get_document_file_streams_with_auth(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "documents_dir", tmp_path)
    monkeypatch.setattr(settings, "auth_required", True)
    from spark.storage import get_storage

    get_storage.cache_clear()

    backend = LocalStorageBackend(
        documents_dir=tmp_path,
        machines_dir=tmp_path / "machines",
        feedback_dir=tmp_path / "feedback",
    )
    doc_id = uuid.uuid4()
    uri = await backend.save_document(
        doc_id,
        "sample.pdf",
        io.BytesIO(b"%PDF sample"),
        factory_id="F-01",
        document_type="machine_manual",
        machine_id=None,
        content_type="application/pdf",
    )

    try:
        from sqlalchemy import select

        from spark.core.database import AsyncSessionLocal
        from spark.db.models.docs import Document

        async with AsyncSessionLocal() as session:
            existing = await session.scalar(select(Document).where(Document.doc_id == doc_id))
            if existing:
                await session.delete(existing)
                await session.commit()

            doc = Document(
                doc_id=doc_id,
                factory_id="F-01",
                document_category="knowledge",
                document_type="machine_manual",
                title="Test PDF",
                source_file="sample.pdf",
                original_filename="sample.pdf",
                mime_type="application/pdf",
                storage_uri=uri,
                ingest_status="completed",
            )
            session.add(doc)
            await session.commit()
    except Exception:
        pytest.skip("Postgres unavailable for document file integration test")

    token = _operator_token()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get(
            f"/api/v1/documents/{doc_id}/file",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 200
        assert res.headers.get("content-type", "").startswith("application/pdf")
        assert b"%PDF" in res.content

        other_token = issue_token(
            {
                "sub": "00000000-0000-0000-0000-000000000099",
                "username": "viewer_f02",
                "roles": ["employee"],
                "factory_access": {"F-02": "read"},
                "token_version": 0,
            }
        )
        denied = await client.get(
            f"/api/v1/documents/{doc_id}/file",
            headers={"Authorization": f"Bearer {other_token}"},
        )
        assert denied.status_code == 403
