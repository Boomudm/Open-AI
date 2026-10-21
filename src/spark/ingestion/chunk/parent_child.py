"""Parent-child chunking with section_path attribution."""

from __future__ import annotations

import uuid
from dataclasses import replace

from spark.ingestion.chunk.section_path import section_path_for_chunk
from spark.ingestion.chunk.stable_id import (
    coerce_doc_id,
    section_path_tuple,
    stable_chunk_id,
    stable_parent_chunk_id,
)
from spark.ingestion.chunk.types import ChunkLeaf
from spark.ingestion.chunking.recursive import recursive_chunk_text


class ParentChildChunker:
    """Structure-aware parent sections with child leaves and section_path."""

    def split(self, text: str, *, chunk_size: int, chunk_overlap: int) -> list[str]:
        leaves = self.split_hierarchy(
            text,
            child_chunk_size=chunk_size,
            child_chunk_overlap=chunk_overlap,
        )
        return [leaf.text for leaf in leaves]

    def split_hierarchy(
        self,
        text: str,
        *,
        parent_chunk_size: int = 2400,
        parent_chunk_overlap: int = 64,
        child_chunk_size: int = 512,
        child_chunk_overlap: int = 64,
        doc_id: uuid.UUID | str | None = None,
    ) -> list[ChunkLeaf]:
        if not text.strip():
            return []

        doc_uuid = coerce_doc_id(doc_id)
        parent_sections = recursive_chunk_text(
            text,
            chunk_size=parent_chunk_size,
            chunk_overlap=parent_chunk_overlap,
        )
        if not parent_sections:
            return []

        leaves: list[ChunkLeaf] = []
        search_start = 0
        for parent_index, parent_text in enumerate(parent_sections):
            parent_text = parent_text.strip()
            if not parent_text:
                continue
            parent_path, search_start = section_path_for_chunk(text, parent_text, search_start)
            path_tuple = section_path_tuple(parent_path)
            if doc_uuid is not None:
                parent_chunk_id = str(stable_parent_chunk_id(doc_uuid, path_tuple))
            else:
                parent_chunk_id = str(uuid.uuid4())

            children = recursive_chunk_text(
                parent_text,
                chunk_size=child_chunk_size,
                chunk_overlap=child_chunk_overlap,
            )
            if not children:
                children = [parent_text]
            child_search = text.find(parent_text, max(0, search_start - len(parent_text)))
            if child_search < 0:
                child_search = search_start
            for child_index, child_text in enumerate(children):
                child_text = child_text.strip()
                if not child_text:
                    continue
                child_path, _ = section_path_for_chunk(text, child_text, child_search)
                leaf = ChunkLeaf(
                    text=child_text,
                    parent_text=parent_text,
                    parent_index=parent_index,
                    child_index=child_index,
                    parent_chunk_id=parent_chunk_id,
                    section_path=child_path or parent_path,
                )
                if doc_uuid is not None:
                    leaf = replace(
                        leaf,
                        chunk_id=str(
                            stable_chunk_id(
                                doc_uuid,
                                section_path_tuple(leaf.section_path),
                                child_index,
                            )
                        ),
                    )
                leaves.append(leaf)
                child_search = text.find(child_text, child_search) + len(child_text)
        return leaves
