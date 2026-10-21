"""Magic-byte MIME validation at upload."""

from __future__ import annotations

import pytest

from spark.services.document_mime import validate_upload_mime


def test_pdf_magic_bytes_accepted() -> None:
    pdf_header = b"%PDF-1.4\n% fake body"
    mime = validate_upload_mime("manual.pdf", pdf_header)
    assert mime == "application/pdf"


def test_exe_renamed_as_pdf_rejected() -> None:
    exe_bytes = b"MZ" + b"\x00" * 64
    with pytest.raises(ValueError, match="MIME mismatch|not allowed"):
        validate_upload_mime("manual.pdf", exe_bytes)


def test_text_renamed_as_pdf_rejected() -> None:
    with pytest.raises(ValueError, match="file signature"):
        validate_upload_mime("manual.pdf", b"not actually a PDF")
