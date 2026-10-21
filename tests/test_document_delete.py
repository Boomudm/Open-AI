"""Document delete endpoint RBAC tests."""

from __future__ import annotations

import io
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from spark.core.auth import issue_token
from spark.core.config import settings
from spark.core.security import Principal, can_write_factory
from spark.main import app
from spark.storage.local import LocalStorageBackend


def test_can_write_factory_operator_role() -> None:
    operator = Principal(
        user_id="u1",
        username="op",
        roles=("operator",),
        factory_access={"F-01": "read"},
    )
    assert can_write_factory(operator, "F-01") is True


def _writer_token() -> str:
    return issue_token(
        {
            "sub": str(uuid.uuid4()),
            "username": "lead_f01",
            "roles": ["operator"],
            "factory_access": {"F-01": "write"},
            "token_version": 0,
        }
    )


def _reader_token() -> str:
    return issue_token(
        {
            "sub": str(uuid.uuid4()),
            "username": "emp_f01",
            "roles": ["employee"],
            "factory_access": {"F-01": "read"},
            "token_version": 0,
        }
    )


async def _seed_document(tmp_path: Path, doc_id: uuid.UUID) -> str:
    from sqlalchemy import select

    from spark.core.database import AsyncSessionLocal
    from spark.db.models.docs import Document
    from spark.storage import get_storage

    get_storage.cache_clear()
    backend = LocalStorageBackend(
        documents_dir=tmp_path,
        machines_dir=tmp_path / "machines",
        feedback_dir=tmp_path / "feedback",
    )
    uri = await backend.save_document(
        doc_id,
        "sample.pdf",
        io.BytesIO(b"%PDF sample"),
        factory_id="F-01",
        document_type="machine_manual",
        machine_id=None,
        content_type="application/pdf",
    )

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
            title="Test doc",
            source_file="sample.pdf",
            original_filename="sample.pdf",
            mime_type="application/pdf",
            storage_uri=uri,
            ingest_status="completed",
        )
        session.add(doc)
        await session.commit()
    return uri


@pytest.mark.asyncio
async def test_delete_document_writer_ok(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "documents_dir", tmp_path)
    monkeypatch.setattr(settings, "auth_required", True)
    monkeypatch.setattr(
        "spark.core.security._validate_token_freshness",
        AsyncMock(return_value=None),
    )

    doc_id = uuid.uuid4()
    try:
        await _seed_document(tmp_path, doc_id)
    except Exception as exc:
        pytest.skip(f"Postgres unavailable: {exc}")

    transport = ASGITransport(app=app)
    with patch(
        "spark.api.v1.endpoints.documents.QdrantRouter.delete_by_doc",
        new_callable=AsyncMock,
    ) as mock_delete:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.delete(
                f"/api/v1/documents/{doc_id}",
                headers={"Authorization": f"Bearer {_writer_token()}"},
            )
        assert res.status_code == 204
        mock_delete.assert_awaited_once()

    from spark.core.database import AsyncSessionLocal
    from spark.db.models.docs import Document

    async with AsyncSessionLocal() as session:
        gone = await session.get(Document, doc_id)
        assert gone is None

    monkeypatch.setattr(settings, "auth_required", False)


@pytest.mark.asyncio
async def test_delete_document_read_only_forbidden(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "documents_dir", tmp_path)
    monkeypatch.setattr(settings, "auth_required", True)
    monkeypatch.setattr(
        "spark.core.security._validate_token_freshness",
        AsyncMock(return_value=None),
    )

    doc_id = uuid.uuid4()
    try:
        await _seed_document(tmp_path, doc_id)
    except Exception as exc:
        pytest.skip(f"Postgres unavailable: {exc}")

    transport = ASGITransport(app=app)
    with patch(
        "spark.api.v1.endpoints.documents.QdrantRouter.delete_by_doc",
        new_callable=AsyncMock,
    ):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.delete(
                f"/api/v1/documents/{doc_id}",
                headers={"Authorization": f"Bearer {_reader_token()}"},
            )
        assert res.status_code == 403

    monkeypatch.setattr(settings, "auth_required", False)
