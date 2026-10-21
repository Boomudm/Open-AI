#!/usr/bin/env python3
"""Batch ingest CLI — same upload validation as POST /ingest/file per manifest item."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import io
import json
import sys
import uuid
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _load_manifest(path: Path) -> list[dict]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        files = raw.get("files") or []
    elif isinstance(raw, list):
        files = raw
    else:
        raise ValueError("manifest must be a list or {files: [...]}")
    if not isinstance(files, list) or not files:
        raise ValueError("manifest files list is empty")
    return [dict(item) for item in files if isinstance(item, dict)]


def _validate_item(item: dict) -> tuple[Path, str, str, str | None, bytes, str]:
    path = Path(str(item.get("path") or ""))
    factory_id = str(item.get("factory_id") or "").strip()
    doc_type = str(item.get("doc_type") or item.get("document_type") or "").strip()
    machine_id_raw = item.get("machine_id")
    machine_id = str(machine_id_raw).strip() if machine_id_raw else None

    if not path.is_file():
        raise ValueError("file_not_found")
    if not factory_id or not doc_type:
        raise ValueError("missing_factory_or_doc_type")

    from spark.core.config import settings
    from spark.ingestion.config_loader import load_config
    from spark.services.document_mime import validate_upload_mime

    load_config(doc_type)
    raw_bytes = path.read_bytes()
    if len(raw_bytes) > settings.max_upload_bytes:
        raise ValueError("file_too_large")
    mime = validate_upload_mime(path.name, raw_bytes)
    return path, factory_id, doc_type, machine_id, raw_bytes, mime


async def _enqueue_item(
    path: Path,
    *,
    factory_id: str,
    doc_type: str,
    machine_id: str | None,
    raw_bytes: bytes,
    mime: str,
    fresh: bool,
) -> str:
    from spark.core.database import AsyncSessionLocal
    from spark.db.models.docs import Document
    from spark.db.models.ingestion import IngestionJob
    from spark.ingestion.config_loader import load_config
    from spark.services.ingest_dedup import resolve_or_create_doc_id
    from spark.storage import get_storage
    from spark.workers.tasks import ingest_document_task

    config = load_config(doc_type)
    file_hash = _hash_bytes(raw_bytes)
    storage = get_storage()

    async with AsyncSessionLocal() as session:
        if fresh:
            doc_id, existing = uuid.uuid4(), None
        else:
            doc_id, existing, _is_reingest = await resolve_or_create_doc_id(
                session,
                factory_id=factory_id,
                file_hash=file_hash,
                machine_id=machine_id,
                document_type=doc_type,
                document_category=config.get("document_category"),
            )
        if existing is None:
            storage_uri = await storage.save_document(
                doc_id,
                path.name,
                io.BytesIO(raw_bytes),
                factory_id=factory_id,
                document_type=doc_type,
                machine_id=machine_id,
                content_type=mime,
            )
            doc = Document(
                doc_id=doc_id,
                factory_id=factory_id,
                machine_id=machine_id,
                document_category=config.get("document_category"),
                document_type=doc_type,
                title=path.name,
                source_file=path.name,
                original_filename=path.name,
                mime_type=mime,
                storage_uri=storage_uri,
                file_hash_sha256=file_hash,
                file_size_bytes=len(raw_bytes),
                ingest_status="pending",
            )
            session.add(doc)
        else:
            storage_uri = existing.storage_uri
            if not storage_uri or not await storage.exists(storage_uri):
                storage_uri = await storage.save_document(
                    doc_id,
                    path.name,
                    io.BytesIO(raw_bytes),
                    factory_id=factory_id,
                    document_type=doc_type,
                    machine_id=machine_id,
                    content_type=mime,
                )
                existing.storage_uri = storage_uri
                existing.file_size_bytes = len(raw_bytes)

        job = IngestionJob(
            job_id=uuid.uuid4(),
            doc_id=doc_id,
            document_type=doc_type,
            original_filename=path.name,
            file_size_bytes=len(raw_bytes),
            factory_id=factory_id,
            machine_id=machine_id,
            status="queued",
        )
        session.add(job)
        await session.flush()
        context = {
            "factory_id": factory_id,
            "machine_id": machine_id,
            "document_type": doc_type,
            "document_category": config.get("document_category"),
            "language": "th",
            "title": path.name,
            "source_file": path.name,
            "file_hash_sha256": file_hash,
        }
        async_result = ingest_document_task.delay(
            doc_id=str(doc_id),
            storage_uri=storage_uri,
            document_type=doc_type,
            document_context=context,
            job_id=str(job.job_id),
        )
        job.celery_task_id = async_result.id
        await session.commit()
        return str(job.job_id)


async def _run(manifest: Path, *, dry_run: bool, fresh: bool) -> dict:
    items = _load_manifest(manifest)
    accepted = 0
    rejected: list[dict[str, str]] = []
    job_ids: list[str] = []
    by_factory: dict[str, int] = {}

    for item in items:
        try:
            _path, factory_id, _doc_type, _machine_id, _raw, _mime = _validate_item(item)
            by_factory[factory_id] = by_factory.get(factory_id, 0) + 1
        except Exception:
            continue

    if not dry_run:
        from spark.services.ingest_rate_limit import check_batch_rate_limit

        for factory_id, count in by_factory.items():
            await check_batch_rate_limit(factory_id, count)

    for item in items:
        try:
            path, factory_id, doc_type, machine_id, raw_bytes, mime = _validate_item(item)
        except ValueError as exc:
            rejected.append({"path": str(item.get("path") or ""), "reason": str(exc)})
            continue
        except Exception as exc:
            rejected.append({"path": str(item.get("path") or ""), "reason": str(exc)[:120]})
            continue

        if dry_run:
            accepted += 1
            continue

        job_id = await _enqueue_item(
            path,
            factory_id=factory_id,
            doc_type=doc_type,
            machine_id=machine_id,
            raw_bytes=raw_bytes,
            mime=mime,
            fresh=fresh,
        )
        job_ids.append(job_id)
        accepted += 1

    return {"accepted": accepted, "rejected": rejected, "job_ids": job_ids}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate or queue batch ingest from YAML manifest")
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--dry-run", action="store_true", help="Validate only")
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="Always create new document rows instead of reusing same-hash documents",
    )
    args = parser.parse_args(argv)
    summary = asyncio.run(_run(args.manifest, dry_run=args.dry_run, fresh=args.fresh))
    print(json.dumps(summary, indent=2))
    return 0 if not summary["rejected"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
