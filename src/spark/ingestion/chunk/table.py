"""TableObject → single embeddable chunk."""

from __future__ import annotations

import uuid

from spark.ingestion.chunk.stable_id import (
    coerce_doc_id,
    section_path_tuple,
    stable_chunk_id,
    stable_parent_chunk_id,
)
from spark.ingestion.chunk.types import ChunkLeaf
from spark.ingestion.parse.table_object import TableObject


def table_to_leaf(
    table: TableObject,
    *,
    doc_id: uuid.UUID | str | None = None,
    leaf_index: int | None = None,
) -> ChunkLeaf:
    text = table.to_embed_text()
    section_path = f"Table {table.table_index}"
    doc_uuid = coerce_doc_id(doc_id)
    if doc_uuid is not None:
        path_tuple = section_path_tuple(section_path)
        index = int(leaf_index if leaf_index is not None else table.table_index)
        parent_id = str(stable_parent_chunk_id(doc_uuid, path_tuple))
        chunk_id = str(stable_chunk_id(doc_uuid, path_tuple, index))
    else:
        parent_id = str(uuid.uuid4())
        chunk_id = None
    return ChunkLeaf(
        text=text,
        parent_text=text,
        parent_index=0,
        child_index=0,
        parent_chunk_id=parent_id,
        section_path=section_path,
        block_type="table",
        chunk_id=chunk_id,
    )


class TableChunker:
    """Keep markdown table blocks atomic; recursive split elsewhere."""

    def split(self, text: str, *, chunk_size: int, chunk_overlap: int) -> list[str]:
        from spark.ingestion.chunking.structure import split_table_atomic

        return split_table_atomic(text, chunk_size=chunk_size, chunk_overlap=chunk_overlap)

