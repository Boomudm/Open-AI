"""Deprecated — use spark.retrieval.candidates."""

from spark.retrieval.candidates import (
    doc_chunk_id,
    generation_context_for_doc,
    group_docs_for_generation,
    hydrate_parent_content_from_pg,
)

__all__ = [
    "doc_chunk_id",
    "generation_context_for_doc",
    "group_docs_for_generation",
    "hydrate_parent_content_from_pg",
]
