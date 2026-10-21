"""Qdrant payload filters for vector retrieval.

When ``rag_acl_filter_mode`` is ``payload_acl``, Qdrant ``factory_id`` / position fields
are the authoritative ACL boundary at retrieval time; the app-layer Redis doc-id cache is
advisory only and not used for Qdrant filtering.
"""

from __future__ import annotations

from datetime import datetime, timezone

from qdrant_client.models import FieldCondition, Filter, IsEmptyCondition, MatchAny, MatchValue, Range

from spark.ingestion.embed_profile import EmbedProfile
from spark.retrieval.models import RAGFilter


def _epoch_day_today() -> int:
    today = datetime.now(tz=timezone.utc).date()
    return today.toordinal() - datetime(1970, 1, 1).toordinal()


def build_qdrant_filter(
    rf: RAGFilter,
    allowed_doc_ids: list[str] | None = None,
    *,
    job_position_ids: list[str] | None = None,
) -> Filter | None:
    from spark.core.config import settings

    must: list[FieldCondition | Filter] = []
    use_payload_acl = settings.rag_acl_filter_mode == "payload_acl"
    if use_payload_acl and job_position_ids is not None:
        if job_position_ids:
            must.append(
                Filter(
                    should=[
                        IsEmptyCondition(is_empty={"key": "restricted_position_ids"}),
                        FieldCondition(
                            key="restricted_position_ids",
                            match=MatchAny(any=[str(item) for item in job_position_ids]),
                        ),
                    ]
                )
            )
    elif allowed_doc_ids is not None:
        must.append(
            FieldCondition(key="doc_id", match=MatchAny(any=allowed_doc_ids))
        )
    if rf.factory_id:
        must.append(FieldCondition(key="factory_id", match=MatchValue(value=rf.factory_id)))
    if rf.machine_id:
        must.append(
            Filter(
                should=[
                    FieldCondition(key="machine_id", match=MatchValue(value=rf.machine_id)),
                    IsEmptyCondition(is_empty={"key": "machine_id"}),
                ]
            )
        )
    if rf.document_category:
        must.append(
            FieldCondition(key="document_category", match=MatchValue(value=rf.document_category))
        )
    if rf.document_type:
        must.append(FieldCondition(key="document_type", match=MatchValue(value=rf.document_type)))
    if rf.revision:
        must.append(FieldCondition(key="revision", match=MatchValue(value=rf.revision)))
    if rf.drawing_no:
        must.append(FieldCondition(key="drawing_no", match=MatchValue(value=rf.drawing_no)))
    if rf.language:
        must.append(FieldCondition(key="language", match=MatchValue(value=rf.language)))

    if rf.only_active:
        today_ord = _epoch_day_today()
        must.append(
            Filter(
                should=[
                    FieldCondition(key="expiry_date", range=Range(gte=today_ord)),
                    IsEmptyCondition(is_empty={"key": "expiry_date"}),
                ]
            )
        )

    must.append(
        Filter(
            should=[
                FieldCondition(key="retrieval_enabled", match=MatchValue(value=True)),
                IsEmptyCondition(is_empty={"key": "retrieval_enabled"}),
            ]
        )
    )

    embed_profile = EmbedProfile.from_runtime()
    must.append(
        FieldCondition(
            key="embed_model_version",
            match=MatchValue(value=embed_profile.version),
        )
    )

    if not must:
        return None
    return Filter(must=must)


def build_exact_tag_filter(
    tag: str,
    rf: RAGFilter,
    allowed_doc_ids: list[str] | None = None,
    *,
    job_position_ids: list[str] | None = None,
) -> Filter:
    """Exact-match filter for a literal PLC/IO symlink tag (e.g. "RES0.BELT_CALIB_SENSOR").

    Matches the tag against either side of the bilateral symlink row
    (``src_path``/``tgt_path``), scoped to io_mapping documents — used to
    guarantee the correct row is retrieved regardless of embedding similarity
    across hundreds of structurally-similar rows.

    Composes on top of ``build_qdrant_filter`` so every retrieval boundary the
    hybrid leg enforces (factory_id tenancy, document ACL, retrieval_enabled
    quarantine, machine/language scoping, active-revision windows) applies to
    the exact-match leg identically. With the default single-collection shard
    strategy a bare tag filter would leak io_mapping rows across factories.

    ``src_path``/``tgt_path`` are stored lowercased (see QdrantWriter), so the
    lookup is case-insensitive for technicians typing tags from memory.
    """
    base = build_qdrant_filter(rf, allowed_doc_ids, job_position_ids=job_position_ids)
    must: list[FieldCondition | Filter] = list(base.must) if base and base.must else []
    if rf.document_type != "io_mapping":
        # If the caller already filters to another document_type, the combined
        # filter is intentionally unsatisfiable — the user's explicit type
        # filter must never be widened by the tag shortcut.
        must.append(
            FieldCondition(key="document_type", match=MatchValue(value="io_mapping"))
        )
    normalized_tag = tag.strip().lower()
    must.append(
        Filter(
            should=[
                FieldCondition(key="src_path", match=MatchValue(value=normalized_tag)),
                FieldCondition(key="tgt_path", match=MatchValue(value=normalized_tag)),
            ]
        )
    )
    return Filter(must=must)
