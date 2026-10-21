"""Ingest pre-flight validation — reject before Celery enqueue (Phase 14)."""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from spark.core.config import settings
from spark.ingestion.budget import ResourceBudget, budget_from_config
from spark.ingestion.config_loader import load_config
from spark.ingestion.config_resolver import resolve_ingest_config
from spark.ingestion.document_type_resolver import resolve_document_type
from spark.services.document_mime import validate_upload_mime


@dataclass
class PolicyHint:
    rule_id: str
    severity: str
    message: str


@dataclass
class PreflightResult:
    accepted: bool
    reasons: list[str] = field(default_factory=list)
    estimated_pages: int | None = None
    estimated_chunks: int | None = None
    ocr_required: bool = False
    budget: ResourceBudget | None = None
    policy_hints: list[PolicyHint] = field(default_factory=list)
    document_type: str | None = None
    factory_id: str | None = None
    quality_tags: list[str] = field(default_factory=list)


def _estimate_pdf_pages(raw_bytes: bytes) -> tuple[int, bool]:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(raw_bytes))
    page_count = len(reader.pages)
    ocr_required = True
    sampled = 0
    sparse = 0
    for page in reader.pages[: min(page_count, 5)]:
        sampled += 1
        text = page.extract_text() or ""
        if len(text.strip()) < 20:
            sparse += 1
    if sampled:
        ocr_required = sparse >= max(1, sampled // 2)
    return page_count, ocr_required


def _estimate_chunks(page_count: int, config: dict[str, Any]) -> int:
    chunking = config.get("chunking") or {}
    child_size = int(chunking.get("child_chunk_size") or chunking.get("chunk_size") or 512)
    avg_chars_per_page = 1800
    total_chars = page_count * avg_chars_per_page
    return max(1, total_chars // max(child_size, 1))


def _text_sample(raw_bytes: bytes, filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf":
        from pypdf import PdfReader

        try:
            reader = PdfReader(io.BytesIO(raw_bytes))
            if not reader.pages:
                return ""
            return (reader.pages[0].extract_text() or "")[:8000]
        except Exception:
            return ""
    try:
        return raw_bytes.decode("utf-8", errors="ignore")[:8000]
    except Exception:
        return ""


def _trust_dry_run(text: str, *, document_type: str) -> list[PolicyHint]:
    if not text.strip():
        return []
    from spark.ingestion.trust.rules_injection import scan_injection_patterns
    from spark.ingestion.trust.rules_secrets import scan_secrets
    from spark.ingestion.trust.scanner import load_content_policy

    rules = (load_content_policy().get("rules") or {}) if isinstance(load_content_policy(), dict) else {}
    findings = list(scan_secrets(text))
    findings.extend(scan_injection_patterns(text, list(rules.get("injection_patterns") or [])))
    return [
        PolicyHint(rule_id=f.rule_id, severity=f.severity, message=f.message)
        for f in findings[:10]
    ]


def run_ingest_preflight(
    *,
    filename: str,
    raw_bytes: bytes,
    document_type: str | None,
    factory_id: str | None,
    machine_id: str | None,
    factory_cfg: dict[str, Any] | None = None,
) -> PreflightResult:
    reasons: list[str] = []
    policy_hints: list[PolicyHint] = []

    if not filename:
        return PreflightResult(accepted=False, reasons=["missing filename"])

    resolved_type = resolve_document_type(filename, document_type, content=raw_bytes)
    if not resolved_type:
        return PreflightResult(
            accepted=False,
            reasons=[f"cannot resolve document_type for {filename}"],
        )

    try:
        config = load_config(resolved_type)
    except FileNotFoundError:
        return PreflightResult(accepted=False, reasons=["unknown document type configuration"])

    quality_tags: list[str] = []

    if len(raw_bytes) > settings.max_upload_bytes:
        reasons.append(f"file exceeds max size of {settings.max_upload_bytes} bytes")

    try:
        validate_upload_mime(filename, raw_bytes)
    except ValueError as exc:
        reasons.append(str(exc))

    resolved_cfg = resolve_ingest_config(resolved_type, factory_cfg or {})
    budget = budget_from_config(resolved_cfg.raw)

    estimated_pages: int | None = None
    estimated_chunks: int | None = None
    ocr_required = False

    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf":
        try:
            estimated_pages, ocr_required = _estimate_pdf_pages(raw_bytes)
        except Exception:
            # Quality issue, not a security/type boundary — accept and tag so
            # the document still gets a chance to ingest (parser may still
            # recover pages OCR-side); it is not silently dropped.
            quality_tags.append("unreadable_or_invalid_pdf_estimate")
            estimated_pages = None
            ocr_required = False
        else:
            estimated_chunks = _estimate_chunks(estimated_pages, resolved_cfg.raw)
            if budget.max_pages is not None and estimated_pages > budget.max_pages:
                reasons.append(
                    f"estimated_pages {estimated_pages} exceeds budget.max_pages {budget.max_pages}"
                )
            if budget.max_chunks is not None and estimated_chunks > budget.max_chunks:
                reasons.append(
                    f"estimated_chunks {estimated_chunks} exceeds budget.max_chunks {budget.max_chunks}"
                )
            if budget.max_ocr_pages is not None and ocr_required and estimated_pages > budget.max_ocr_pages:
                reasons.append(
                    f"ocr_required with {estimated_pages} pages exceeds budget.max_ocr_pages {budget.max_ocr_pages}"
                )

    if "machine_id" in (config.get("required_metadata") or []) and not machine_id:
        quality_tags.append("missing_recommended_metadata:machine_id")

    sample = _text_sample(raw_bytes, filename)
    # Policy hints are surfaced to the uploader as warnings only — content
    # scanning never rejects an upload (see trust/gate.py). Resource-budget
    # limits above remain hard rejects (runaway parse/embed cost, not quality).
    policy_hints = _trust_dry_run(sample, document_type=resolved_type)

    return PreflightResult(
        accepted=len(reasons) == 0,
        reasons=reasons,
        estimated_pages=estimated_pages,
        estimated_chunks=estimated_chunks,
        ocr_required=ocr_required,
        budget=budget
        if any(
            (
                budget.max_pages,
                budget.max_chunks,
                budget.max_embed_tokens,
                budget.max_ocr_pages,
            )
        )
        else None,
        policy_hints=policy_hints,
        quality_tags=quality_tags,
        document_type=resolved_type,
        factory_id=factory_id,
    )
