"""Phase 14 — ingest preflight rejects bad uploads before queue."""

from __future__ import annotations

from spark.ingestion.preflight.validator import run_ingest_preflight


def test_preflight_rejects_oversized_file(monkeypatch) -> None:
    from spark.core.config import settings

    monkeypatch.setattr(settings, "max_upload_bytes", 100)
    result = run_ingest_preflight(
        filename="notes.txt",
        raw_bytes=b"x" * 200,
        document_type="machine_manual",
        factory_id="F-01",
        machine_id=None,
    )
    assert result.accepted is False
    assert any("exceeds max size" in r for r in result.reasons)


def test_preflight_rejects_unknown_extension() -> None:
    result = run_ingest_preflight(
        filename="data.xyzunknown",
        raw_bytes=b"hello",
        document_type=None,
        factory_id="F-01",
        machine_id=None,
    )
    assert result.accepted is False


def test_preflight_rejects_non_pdf_bytes_via_mime_check_without_crashing() -> None:
    """Junk bytes with a .pdf extension are still rejected — by MIME/signature
    validation (a real security boundary), not by the PDF-parse quality check."""
    result = run_ingest_preflight(
        filename="manual.pdf",
        raw_bytes=b"not a pdf",
        document_type="machine_manual",
        factory_id="F-01",
        machine_id="MC-001",
    )
    assert result.accepted is False
    assert any("MIME mismatch" in r for r in result.reasons)


def test_preflight_tags_unparseable_pdf_instead_of_rejecting() -> None:
    """A correctly-signed but structurally broken PDF is accepted and tagged
    (product decision 2026-07: quality issues never hard-block ingest,
    including for safety document types) rather than rejected outright."""
    pdf_signature_but_truncated = b"%PDF-1.4\n" + b"garbage" * 20
    result = run_ingest_preflight(
        filename="manual.pdf",
        raw_bytes=pdf_signature_but_truncated,
        document_type="machine_manual",
        factory_id="F-01",
        machine_id="MC-001",
    )
    assert result.accepted is True
    assert "unreadable_or_invalid_pdf_estimate" in result.quality_tags


def test_preflight_flags_secrets_as_warning_not_reject() -> None:
    """Content scanning is observability only — the uploader sees the hint but
    the upload proceeds (product decision 2026-07; see trust/gate.py)."""
    result = run_ingest_preflight(
        filename="notes.txt",
        raw_bytes=b"backup key AKIAIOSFODNN7EXAMPLE stored here",
        document_type="machine_manual",
        factory_id="F-01",
        machine_id=None,
    )
    assert result.accepted is True
    assert not any(r.startswith("policy:") for r in result.reasons)
    assert result.policy_hints


def test_preflight_accepts_clean_text() -> None:
    result = run_ingest_preflight(
        filename="notes.txt",
        raw_bytes=b"Routine maintenance checklist for conveyor belt MC-001.",
        document_type="machine_manual",
        factory_id="F-01",
        machine_id="MC-001",
    )
    assert result.accepted is True
    assert result.reasons == []
