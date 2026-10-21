from __future__ import annotations

import uuid

import pytest

from spark.storage.keys import (
    chat_attachment_object_key,
    document_object_key,
    feedback_photo_object_key,
    machine_image_object_key,
    sanitize_segment,
)


def test_sanitize_segment() -> None:
    assert sanitize_segment("F-01") == "F-01"
    assert sanitize_segment("machine/manual") == "machine-manual"
    assert sanitize_segment(None, fallback="_general") == "_general"
    assert sanitize_segment("  ", fallback="_unknown") == "_unknown"


def test_document_object_key() -> None:
    doc_id = uuid.UUID("11111111-1111-1111-1111-111111111111")
    key = document_object_key(
        factory_id="F-01",
        document_type="machine_manual",
        machine_id="MC-001",
        doc_id=doc_id,
        filename="manual.pdf",
    )
    assert key == (
        "documents/F-01/machine_manual/MC-001/"
        "11111111-1111-1111-1111-111111111111/original.pdf"
    )


def test_document_object_key_general_machine() -> None:
    doc_id = uuid.uuid4()
    key = document_object_key(
        factory_id="F-01",
        document_type="policy",
        machine_id=None,
        doc_id=doc_id,
        filename="policy.docx",
    )
    assert "/_general/" in key


def test_document_object_key_requires_factory() -> None:
    with pytest.raises(ValueError, match="factory_id"):
        document_object_key(
            factory_id="",
            document_type="machine_manual",
            machine_id=None,
            doc_id=uuid.uuid4(),
            filename="a.pdf",
        )


def test_machine_image_object_key() -> None:
    key = machine_image_object_key(factory_id="F-01", machine_id="MC-001", mime="image/png")
    assert key == "machines/F-01/MC-001/cover.png"


def test_feedback_photo_object_key() -> None:
    from datetime import UTC, datetime

    feedback_id = uuid.uuid4()
    created_at = datetime(2026, 6, 15, tzinfo=UTC)
    key = feedback_photo_object_key(
        factory_id="F-01",
        feedback_id=feedback_id,
        created_at=created_at,
        sort_order=0,
        mime="image/jpeg",
    )
    assert key == f"feedback/F-01/2026-06/{feedback_id}/photo-1.jpg"


def test_chat_attachment_object_key() -> None:
    session_id = uuid.UUID("22222222-2222-2222-2222-222222222222")
    message_id = uuid.UUID("33333333-3333-3333-3333-333333333333")
    key = chat_attachment_object_key(
        factory_id="F-01",
        session_id=session_id,
        message_id=message_id,
        sort_order=0,
        mime="image/png",
    )
    assert key == f"chat/F-01/{session_id}/{message_id}/attachment-1.png"
