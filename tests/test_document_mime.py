from __future__ import annotations

from spark.services.document_mime import is_allowed_mime, resolve_document_mime


def test_resolve_document_mime_from_filename_when_stored_null() -> None:
    mime = resolve_document_mime(
        mime_type=None,
        original_filename=None,
        source_file="manual.pdf",
    )
    assert mime == "application/pdf"
    assert is_allowed_mime(mime)


def test_resolve_document_mime_rejects_unknown() -> None:
    mime = resolve_document_mime(
        mime_type=None,
        original_filename="archive.zip",
        source_file="archive.zip",
    )
    assert not is_allowed_mime(mime)
