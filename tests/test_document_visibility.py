"""PATCH document visibility and access side effects."""

from __future__ import annotations

import io
import uuid
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from spark.core.auth import issue_token
from spark.core.config import settings
from spark.core.database import AsyncSessionLocal
from spark.db.models.docs import Document
from spark.db.models.job_positions import JobPosition
from spark.main import app
from spark.services.ingest_scope import set_document_job_positions
from spark.storage import get_storage
from spark.storage.local import LocalStorageBackend


def _token(
    *,
    roles: list[str],
    factory_access: dict[str, str],
    job_position_ids: list[str] | None = None,
) -> str:
    return issue_token(
        {
            "sub": str(uuid.uuid4()),
            "username": "visibility_test",
            "roles": roles,
            "factory_access": factory_access,
            "job_position_ids": job_position_ids or [],
            "token_version": 0,
        }
    )


async def _seed_document(tmp_path: Path, doc_id: uuid.UUID) -> None:
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

        session.add(
            Document(
                doc_id=doc_id,
                factory_id="F-01",
                document_category="knowledge",
                document_type="machine_manual",
                title="Visibility test doc",
                source_file="sample.pdf",
                original_filename="sample.pdf",
                mime_type="application/pdf",
                storage_uri=uri,
                ingest_status="completed",
            )
        )
        await session.commit()


async def _position_ids_by_code(*codes: str) -> list[uuid.UUID]:
    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(
                select(JobPosition.position_id).where(JobPosition.position_code.in_(codes))
            )
        ).scalars().all()
        return list(rows)


@pytest.mark.asyncio
async def test_patch_visibility_restricts_document_access(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "documents_dir", tmp_path)
    monkeypatch.setattr(settings, "auth_required", True)
    monkeypatch.setattr(
        "spark.core.security._validate_token_freshness",
        AsyncMock(return_value=None),
    )

    doc_id = uuid.uuid4()
    try:
        await _seed_document(tmp_path, doc_id)
        positions = await _position_ids_by_code("maintenance_tech", "qc")
    except Exception as exc:
        pytest.skip(f"Postgres unavailable or job positions missing: {exc}")

    if len(positions) < 2:
        pytest.skip("Need at least two seeded job positions")

    tech_id, qc_id = positions[0], positions[1]

    async with AsyncSessionLocal() as session:
        await set_document_job_positions(session, doc_id, [tech_id, qc_id])
        await session.commit()

    writer = _token(roles=["operator"], factory_access={"F-01": "write"})
    reader_qc = _token(
        roles=["employee"],
        factory_access={"F-01": "read"},
        job_position_ids=[str(qc_id)],
    )
    reader_tech = _token(
        roles=["employee"],
        factory_access={"F-01": "read"},
        job_position_ids=[str(tech_id)],
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res_patch = await client.patch(
            f"/api/v1/documents/{doc_id}/visibility",
            headers={"Authorization": f"Bearer {writer}"},
            json={"visible_position_ids": [str(tech_id)]},
        )
        assert res_patch.status_code == 200
        assert res_patch.json()["visible_position_ids"] == [str(tech_id)]

        res_tech = await client.get(
            f"/api/v1/documents/{doc_id}",
            headers={"Authorization": f"Bearer {reader_tech}"},
        )
        assert res_tech.status_code == 200

        res_qc = await client.get(
            f"/api/v1/documents/{doc_id}",
            headers={"Authorization": f"Bearer {reader_qc}"},
        )
        assert res_qc.status_code == 403

    monkeypatch.setattr(settings, "auth_required", False)


@pytest.mark.asyncio
async def test_patch_visibility_unrestricted_allows_all_positions(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "documents_dir", tmp_path)
    monkeypatch.setattr(settings, "auth_required", True)
    monkeypatch.setattr(
        "spark.core.security._validate_token_freshness",
        AsyncMock(return_value=None),
    )

    doc_id = uuid.uuid4()
    try:
        await _seed_document(tmp_path, doc_id)
        positions = await _position_ids_by_code("maintenance_tech")
    except Exception as exc:
        pytest.skip(f"Postgres unavailable: {exc}")

    if not positions:
        pytest.skip("Need seeded job positions")

    tech_id = positions[0]

    async with AsyncSessionLocal() as session:
        await set_document_job_positions(session, doc_id, [tech_id])
        await session.commit()

    writer = _token(roles=["operator"], factory_access={"F-01": "write"})
    reader_qc = _token(
        roles=["employee"],
        factory_access={"F-01": "read"},
        job_position_ids=[str(uuid.uuid4())],
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res_patch = await client.patch(
            f"/api/v1/documents/{doc_id}/visibility",
            headers={"Authorization": f"Bearer {writer}"},
            json={"visible_position_ids": []},
        )
        assert res_patch.status_code == 200
        assert res_patch.json()["visible_position_ids"] == []

        res_reader = await client.get(
            f"/api/v1/documents/{doc_id}",
            headers={"Authorization": f"Bearer {reader_qc}"},
        )
        assert res_reader.status_code == 200

    monkeypatch.setattr(settings, "auth_required", False)


@pytest.mark.asyncio
async def test_patch_visibility_denied_for_read_only(tmp_path: Path, monkeypatch) -> None:
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

    reader = _token(roles=["employee"], factory_access={"F-01": "read"})
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.patch(
            f"/api/v1/documents/{doc_id}/visibility",
            headers={"Authorization": f"Bearer {reader}"},
            json={"visible_position_ids": []},
        )
        assert res.status_code == 403

    monkeypatch.setattr(settings, "auth_required", False)


@pytest.mark.asyncio
async def test_patch_visibility_admin_other_factory(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "documents_dir", tmp_path)
    monkeypatch.setattr(settings, "auth_required", True)
    monkeypatch.setattr(
        "spark.core.security._validate_token_freshness",
        AsyncMock(return_value=None),
    )

    doc_id = uuid.uuid4()
    try:
        await _seed_document(tmp_path, doc_id)
        positions = await _position_ids_by_code("maintenance_tech")
    except Exception as exc:
        pytest.skip(f"Postgres unavailable: {exc}")

    if not positions:
        pytest.skip("Need seeded job positions")

    admin = _token(roles=["admin"], factory_access={})
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.patch(
            f"/api/v1/documents/{doc_id}/visibility",
            headers={"Authorization": f"Bearer {admin}"},
            json={"visible_position_ids": [str(positions[0])]},
        )
        assert res.status_code == 200

    monkeypatch.setattr(settings, "auth_required", False)
