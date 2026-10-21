"""One-time payload migration: legacy → new ``embed_model_version`` format.

Commit 7a2434e changed ``EmbedProfile.version`` from
``{llm_profile}:{model}@{provider}`` to ``{model}@{provider}#{dim}`` because
the old format wrongly baked the *chat* profile name into an *embedding*
identity. Retrieval hard-filters on this payload key, so every point written
before that commit became invisible to search after deploying it — even
though the stored vectors are byte-identical (same model, provider, dim).

This rewrites only the label, never the vectors, and only for values whose
model@provider part matches the currently active embedder. Idempotent.

Usage (host, repo root — reads .env for Qdrant/Postgres endpoints):
    .venv/bin/python scripts/migrate_embed_version_payload.py [--dry-run]
"""

from __future__ import annotations

import argparse
import re
import sys

from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue

from spark.core.config import settings
from spark.ingestion.embed_profile import EmbedProfile

BATCH = 512


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    profile = EmbedProfile.from_runtime()
    new_version = profile.version  # e.g. BAAI/bge-m3@sentence_transformers#1024
    model_at_provider = f"{profile.model_id}@{profile.provider}"
    # Legacy: any "{profile_name}:" prefix followed by the SAME model@provider.
    legacy_re = re.compile(rf"^[^:#]+:{re.escape(model_at_provider)}$")
    print(f"new version : {new_version}")
    print(f"legacy match: <profile>:{model_at_provider}")

    client = QdrantClient(host=settings.qdrant_host, port=settings.qdrant_port, timeout=60)

    total_rewritten = 0
    for coll in [c.name for c in client.get_collections().collections]:
        offset = None
        ids: list[str | int] = []
        skipped_other = 0
        while True:
            points, offset = client.scroll(
                collection_name=coll,
                limit=BATCH,
                offset=offset,
                with_payload=["embed_model_version"],
                with_vectors=False,
            )
            for p in points:
                val = str((p.payload or {}).get("embed_model_version") or "")
                if val == new_version or not val:
                    continue
                if legacy_re.match(val):
                    ids.append(p.id)
                else:
                    skipped_other += 1
            if offset is None:
                break
        if skipped_other:
            print(f"  {coll}: WARNING {skipped_other} points have a DIFFERENT embedder version — left untouched")
        if not ids:
            print(f"  {coll}: nothing to rewrite")
            continue
        if args.dry_run:
            print(f"  {coll}: would rewrite {len(ids)} points")
            continue
        for i in range(0, len(ids), BATCH):
            client.set_payload(
                collection_name=coll,
                payload={"embed_model_version": new_version},
                points=ids[i : i + BATCH],
                wait=True,
            )
        total_rewritten += len(ids)
        print(f"  {coll}: rewrote {len(ids)} points")

    # Postgres mirror column (payload_audit compares it against Qdrant).
    import sqlalchemy as sa

    engine = sa.create_engine(settings.database_url_sync)
    with engine.begin() as conn:
        like = f"%:{model_at_provider}"
        if args.dry_run:
            n = conn.execute(
                sa.text("SELECT count(*) FROM document_chunks WHERE embed_model_version LIKE :like"),
                {"like": like},
            ).scalar()
            print(f"postgres: would rewrite {n} document_chunks rows")
        else:
            res = conn.execute(
                sa.text(
                    "UPDATE document_chunks SET embed_model_version = :new "
                    "WHERE embed_model_version LIKE :like"
                ),
                {"new": new_version, "like": like},
            )
            print(f"postgres: rewrote {res.rowcount} document_chunks rows")

    print(f"done. qdrant points rewritten: {total_rewritten}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
