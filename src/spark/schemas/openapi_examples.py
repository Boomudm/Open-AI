"""Shared OpenAPI examples for the document RAG API."""

from __future__ import annotations

from typing import Any

DEMO_FACTORY = "F-01"
DEMO_MC001 = "MC-001"
DEMO_DOC_ID = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
DEMO_JOB_ID = "b2c3d4e5-f6a7-8901-bcde-f12345678901"
DEMO_SESSION_ID = "c3d4e5f6-a7b8-9012-cdef-123456789012"

RAG_FILTER_MC001: dict[str, Any] = {
    "factory_id": DEMO_FACTORY,
    "document_type": "knowledge_document",
    "only_active": False,
}

RAG_QUERY_OVERHEATING: dict[str, Any] = {
    "question": "เอกสารนี้ระบุขั้นตอนอนุมัติไว้อย่างไร",
    "filter": RAG_FILTER_MC001,
    "top_k": 6,
}

RAG_RESPONSE_OVERHEATING: dict[str, Any] = {
    "answer": "เอกสารระบุขั้นตอนอนุมัติไว้เป็นลำดับ พร้อมผู้รับผิดชอบในแต่ละขั้น [chunk_id:abc123].",
    "sources": [
        {
            "doc_id": DEMO_DOC_ID,
            "title": "Company Policy",
            "source_file": "policy.pdf",
            "page": 3,
            "document_type": "knowledge_document",
            "score": 0.6821,
        }
    ],
    "used_filters": {"factory_id": DEMO_FACTORY},
    "intent": "factual",
    "fallback_level": 0,
}

CHAT_SESSION_CREATE: dict[str, Any] = {"title": "Document Q&A session"}

CHAT_SESSION_OUT: dict[str, Any] = {
    "session_id": DEMO_SESSION_ID,
    "title": "Document Q&A session",
    "context": {"factory_id": DEMO_FACTORY},
}

INGEST_FILE_RESPONSE: dict[str, Any] = {
    "job_id": DEMO_JOB_ID,
    "doc_id": DEMO_DOC_ID,
    "status": "queued",
    "celery_task_id": "celery-task-abc123",
}

INGESTION_JOB: dict[str, Any] = {
    "job_id": DEMO_JOB_ID,
    "doc_id": DEMO_DOC_ID,
    "document_type": "knowledge_document",
    "original_filename": "policy.pdf",
    "file_size_bytes": 1_024_000,
    "factory_id": DEMO_FACTORY,
    "machine_id": None,
    "status": "completed",
    "rows_total": 120,
    "rows_ok": 120,
    "rows_skipped": 0,
    "started_at": "2026-05-24T10:00:00+00:00",
    "finished_at": "2026-05-24T10:05:00+00:00",
    "error_message": None,
}

INGESTION_ERROR: dict[str, Any] = {
    "error_id": "d4e5f6a7-b8c9-0123-def0-234567890123",
    "job_id": DEMO_JOB_ID,
    "row_number": 42,
    "chunk_index": None,
    "reason_code": "missing_required",
    "reason_detail": "required field is empty",
    "raw_payload": {"row_number": 42},
    "created_at": "2026-05-24T10:01:00+00:00",
}

MACHINE_MC001: dict[str, Any] = {
    "machine_id": DEMO_MC001,
    "factory_id": DEMO_FACTORY,
    "machine_name": "Servo Motor Line A",
    "machine_type": "motor",
    "manufacturer": "Mitsubishi",
    "model_number": "MR-J5",
    "install_date": "2022-06-15",
    "is_active": True,
    "notes": None,
    "created_at": "2026-05-24T08:00:00+00:00",
    "updated_at": "2026-05-24T08:00:00+00:00",
}

MACHINE_CREATE: dict[str, Any] = {
    "machine_id": "MC-003",
    "factory_id": DEMO_FACTORY,
    "machine_name": "Conveyor C",
    "machine_type": "conveyor",
}

ALIAS_CREATE: dict[str, Any] = {"alias": "เครื่อง 1", "source": "manual"}

READYZ_OK: dict[str, Any] = {
    "status": "ok",
    "checks": {"postgres": "ok", "qdrant": "ok", "ollama": "ok"},
}

READYZ_DEGRADED: dict[str, Any] = {
    "status": "degraded",
    "checks": {"postgres": "ok", "qdrant": "ok", "ollama": "unreachable"},
}

ERROR_ENVELOPE: dict[str, Any] = {
    "detail": "Request failed",
    "code": "request_failed",
    "retryable": False,
}

ERROR_404: dict[str, Any] = {
    "detail": "Resource not found",
    "code": "not_found",
    "retryable": False,
}

ERROR_422: dict[str, Any] = {
    "detail": "Validation error",
    "code": "validation_error",
    "retryable": False,
}

ERROR_503: dict[str, Any] = {
    "detail": "Dependency unavailable",
    "code": "dependency_unavailable",
    "retryable": True,
}
