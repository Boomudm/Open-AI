"""Collection naming strategy for multi-shard Qdrant deployments.

Demo (≤ 5M chunks): single collection `spark_docs`.
Mid (≤ 50M):        per-factory shard `spark_docs__{factory_id}`.
Large (> 50M):      per-(factory, category) shard.

The strategy is chosen by env var `QDRANT_SHARD_STRATEGY`:
  single | per_factory | per_factory_category
"""

from __future__ import annotations

from typing import Literal

from spark.core.config import settings

ShardStrategy = Literal["single", "per_factory", "per_factory_category"]


def get_strategy() -> ShardStrategy:
    raw = getattr(settings, "qdrant_shard_strategy", "single") or "single"
    if raw not in ("single", "per_factory", "per_factory_category"):
        raise ValueError(f"unknown qdrant shard strategy: {raw}")
    return raw  # type: ignore[return-value]


def collection_suffix_version() -> str:
    return (getattr(settings, "qdrant_collection_suffix_version", "") or "").strip()


def apply_collection_suffix(name: str) -> str:
    suffix = collection_suffix_version()
    if not suffix:
        return name
    return f"{name}__{suffix}"


def collection_for(
    factory_id: str | None,
    document_category: str | None = None,
) -> str:
    base = settings.qdrant_collection
    strategy = get_strategy()
    if strategy == "single" or not factory_id:
        name = base
    elif strategy == "per_factory":
        name = f"{base}__{factory_id.lower()}"
    else:
        cat = (document_category or "misc").lower()
        name = f"{base}__{factory_id.lower()}__{cat}"
    return apply_collection_suffix(name)


def collection_for_document(
    document_type: str | None,
    factory_id: str | None,
    document_category: str | None = None,
) -> str:
    """Collection name for an existing document, honoring its ingest-type override.

    Some document types (configs/ingestion/company_policy.yaml,
    hr_handbook.yaml, internal_guideline.yaml) route to a different
    collection (spark_enterprise_docs) via a `qdrant.collection` override
    that only the ingest pipeline was checking (ingestion/stages/common.py's
    qdrant_collection()). Delete, reconcile, and policy-rescan code paths
    only have the Document row, not a resolved ingest config, so they called
    collection_for() directly and silently missed the override — deleting
    from / reconciling against the wrong (empty) collection while the
    document's real vectors sat orphaned in spark_enterprise_docs forever.
    """
    if document_type:
        try:
            from spark.ingestion.config_loader import load_config

            override = (load_config(document_type).get("qdrant") or {}).get("collection")
            if override and get_strategy() == "single":
                return apply_collection_suffix(str(override))
        except FileNotFoundError:
            pass
    return collection_for(factory_id, document_category)


def known_collections() -> set[str]:
    """Every base collection name this app actually writes to.

    Most document types route to settings.qdrant_collection ("spark_docs"),
    but a few (company_policy, hr_handbook, internal_guideline) route to
    settings.qdrant_enterprise_collection ("spark_enterprise_docs") via a
    per-type config override (see collection_for_document). Any code that
    needs to find/clean up a document's vectors without resolving its full
    ingest config (dashboard stats, generation purge, reconcile) must check
    both bases — checking only settings.qdrant_collection silently misses
    the enterprise collection.
    """
    return {settings.qdrant_collection, settings.qdrant_enterprise_collection}


def mandatory_factory_id_enforced() -> bool:
    """True when production lock requires factory_id at retrieval entrypoints."""
    try:
        from spark.core.production_lock import load_production_lock_manifest

        return load_production_lock_manifest().mandatory_factory_id_enforced
    except FileNotFoundError:
        return False


def validate_factory_id_for_retrieval(factory_id: str | None) -> None:
    """Raise ValueError when factory_id is required but missing."""
    if factory_id:
        return
    if mandatory_factory_id_enforced():
        raise ValueError("factory_id required for retrieval")


def list_search_collections(
    factory_id: str | None,
    document_category: str | None = None,
    *,
    factory_ids: list[str] | None = None,
) -> list[str]:
    """Collections to query during RAG retrieval."""
    strategy = get_strategy()
    if strategy == "single":
        return [settings.qdrant_collection]
    if factory_id:
        return [collection_for(factory_id, document_category)]
    if factory_ids:
        return [collection_for(fid, document_category) for fid in factory_ids]
    validate_factory_id_for_retrieval(factory_id)
    return [settings.qdrant_collection]
