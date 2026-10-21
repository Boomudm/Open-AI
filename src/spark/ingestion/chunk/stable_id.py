"""Deterministic chunk lineage IDs for re-ingest idempotency (Phase 6)."""

from __future__ import annotations

import uuid

# Project-scoped namespace for chunk UUID5 derivation.
STABLE_CHUNK_NAMESPACE = uuid.UUID("f47ac10b-58cc-4372-a567-0e02b2c3d479")


def section_path_tuple(path: str | list[str] | None) -> tuple[str, ...]:
    if path is None:
        return ()
    if isinstance(path, list):
        parts = [str(item).strip() for item in path if str(item).strip()]
    else:
        parts = [part.strip() for part in str(path).split(">") if part.strip()]
    return tuple(parts)


def stable_chunk_id(doc_id: uuid.UUID, section_path: tuple[str, ...], leaf_index: int) -> uuid.UUID:
    path_key = "/".join(section_path)
    return uuid.uuid5(STABLE_CHUNK_NAMESPACE, f"{doc_id}:{path_key}:{leaf_index}")


def stable_parent_chunk_id(doc_id: uuid.UUID, section_path: tuple[str, ...]) -> uuid.UUID:
    path_key = "/".join(section_path)
    return uuid.uuid5(STABLE_CHUNK_NAMESPACE, f"{doc_id}:{path_key}:parent")


def coerce_doc_id(value: object) -> uuid.UUID | None:
    if value is None:
        return None
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError):
        return None
