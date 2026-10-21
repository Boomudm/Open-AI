#!/usr/bin/env python3
"""Drop and recreate Qdrant collections with schema v2 (pre-production only)."""

from __future__ import annotations

import argparse

from spark.core.llm_profile import embedding_dimension
from spark.core.logging import configure_logging, get_logger
from spark.core.qdrant import recreate_collection
from spark.core.qdrant_strategy import list_search_collections

configure_logging()
log = get_logger("qdrant_recreate_collections")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--factory-id",
        action="append",
        default=None,
        help="Limit to factory ids (repeatable). Default: all known factories.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Required confirmation — destructive operation",
    )
    args = parser.parse_args()
    if not args.yes:
        raise SystemExit("Refusing to run without --yes (drops all points in target collections)")

    dim = embedding_dimension()
    collections = list_search_collections(args.factory_id)
    from spark.core.production_profile import ProductionProfile

    profile = ProductionProfile.from_settings()
    for coll in collections:
        recreate_collection(coll, vector_size=dim)
        log.info(
            "collection_recreated",
            collection=coll,
            dim=dim,
            sparse_encoder=profile.sparse_encoder,
        )
    print(
        f"Recreated {len(collections)} collection(s) with dense+sparse schema v2 "
        f"(sparse_encoder={profile.sparse_encoder})"
    )


if __name__ == "__main__":
    main()
