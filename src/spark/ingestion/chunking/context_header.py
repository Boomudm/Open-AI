"""Contextual headers prepended to embedding text only (not stored in page_content)."""

from __future__ import annotations

from typing import Any


def build_chunk_header(ctx: dict[str, Any], payload: dict[str, Any]) -> str:
    """Build a bilingual contextual prefix for embedding (not lexical index text).

    Example: ``Factory F1 / โรงงาน F1 | Machine MC-001 / เครื่อง MC-001 | ...``
    """
    parts: list[str] = []

    factory = payload.get("factory_id") or ctx.get("factory_id")
    if factory:
        parts.append(f"Factory {factory} / โรงงาน {factory}")

    machine = payload.get("machine_id") or ctx.get("machine_id")
    if machine:
        parts.append(f"Machine {machine} / เครื่อง {machine}")

    doc_type = payload.get("document_type") or ctx.get("document_type")
    if doc_type:
        parts.append(f"Type {doc_type}")

    title = payload.get("title") or ctx.get("title") or ctx.get("source_file")
    if title:
        parts.append(f"Title {title}")

    revision = payload.get("revision") or ctx.get("revision")
    if revision:
        parts.append(f"Rev {revision}")

    drawing_no = payload.get("drawing_no") or ctx.get("drawing_no")
    if drawing_no:
        parts.append(f"Drawing {drawing_no}")

    section_path = (
        payload.get("structural_path")
        or payload.get("section_path")
        or payload.get("section")
    )
    if section_path:
        parts.append(f"Section {section_path}")

    page_range = payload.get("page_range")
    if page_range:
        parts.append(f"Pages {page_range}")
    else:
        page = payload.get("page")
        if page is not None:
            parts.append(f"Page {page}")

    return " | ".join(parts)


def embed_text_with_header(
    raw_text: str,
    ctx: dict[str, Any],
    payload: dict[str, Any],
) -> str:
    """Return header + separator + raw text for embedding only.

    ``page_content`` and stored chunk text remain clean for citations.
    """
    header = build_chunk_header(ctx, payload)
    body = (raw_text or "").strip()
    if not header:
        return body
    if not body:
        return header
    return f"{header}\n---\n{body}"
