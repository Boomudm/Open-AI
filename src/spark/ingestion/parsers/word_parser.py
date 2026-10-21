from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from docx import Document as DocxDocument
from docx.table import Table
from docx.text.paragraph import Paragraph

from spark.core.logging import get_logger
from spark.ingestion.chunk.registry import PARSER_VERSION, chunk_blocks, leaf_metadata_fields
from spark.ingestion.config_resolver import get_chunking_config
from spark.ingestion.chunk.strategies import is_parent_child_strategy
from spark.ingestion.parse.blocks import ParsedBlock
from spark.ingestion.parse.table_object import TableObject, table_rows_to_markdown
from spark.ingestion.parsers.base import ParsedRecord, ParserError, ParserPlugin

log = get_logger(__name__)

_HEADING_STYLES = frozenset({"Heading 1", "Heading 2", "Heading 3", "Heading 4", "Title"})


def _iter_block_items(doc: DocxDocument):
    body = doc.element.body
    for child in body.iterchildren():
        tag = child.tag.split("}")[-1]
        if tag == "p":
            yield Paragraph(child, doc)
        elif tag == "tbl":
            yield Table(child, doc)


def _table_to_object(table: Table, table_index: int) -> TableObject | None:
    rows: list[list[str]] = []
    for row in table.rows:
        cells = [c.text.strip() for c in row.cells if c.text and c.text.strip()]
        if cells:
            rows.append(cells)
    if not rows:
        return None
    headers = rows[0]
    data_rows = rows[1:] if len(rows) > 1 else []
    markdown = table_rows_to_markdown([headers] + data_rows) if headers else ""
    dict_rows = [
        {headers[i]: row[i] for i in range(min(len(headers), len(row))) if headers[i]}
        for row in data_rows
    ]
    return TableObject(
        markdown=markdown or table_rows_to_markdown(rows),
        headers=headers,
        rows=dict_rows,
        page=0,
        table_index=table_index,
    )


def _extract_structured_blocks(path: Path) -> tuple[list[ParsedBlock], list[TableObject]]:
    doc = DocxDocument(str(path))
    blocks: list[ParsedBlock] = []
    tables: list[TableObject] = []
    section_path: list[str] = []
    table_index = 0
    order = 0

    for item in _iter_block_items(doc):
        if isinstance(item, Paragraph):
            text = (item.text or "").strip()
            if not text:
                continue
            style_name = item.style.name if item.style else ""
            if style_name in _HEADING_STYLES:
                section_path = [text]
                block_type = "heading"
            else:
                block_type = "paragraph"
            blocks.append(
                ParsedBlock(
                    block_type=block_type,
                    text=text,
                    page=None,
                    reading_order=order,
                    section_path=list(section_path),
                    metadata={"extraction_source": "word", "parser_version": PARSER_VERSION},
                )
            )
            order += 1
        elif isinstance(item, Table):
            table_index += 1
            table_obj = _table_to_object(item, table_index)
            if table_obj is not None:
                tables.append(table_obj)
                blocks.append(
                    ParsedBlock(
                        block_type="table",
                        text=table_obj.markdown,
                        page=None,
                        reading_order=order,
                        section_path=list(section_path),
                        metadata={
                            "extraction_source": "word",
                            "parser_version": PARSER_VERSION,
                            "table_object": table_obj,
                        },
                    )
                )
                order += 1

    return blocks, tables


class WordParser(ParserPlugin):
    name = "word"
    supported_extensions = (".docx",)

    async def parse(self, file_path: Path, config: dict[str, Any]) -> AsyncIterator[ParsedRecord]:
        if file_path.suffix.lower() == ".doc":
            raise ParserError(
                "unsupported_file_type",
                "Legacy .doc format is not supported; convert to .docx before upload",
            )

        loop = asyncio.get_running_loop()
        try:
            blocks, table_objects = await loop.run_in_executor(
                None, _extract_structured_blocks, file_path
            )
        except Exception as exc:
            raise ParserError("parser_failed", f"cannot read Word document: {exc}") from exc

        chunking = get_chunking_config(config)
        strategy = chunking.get("strategy")
        mode = (chunking.get("mode") or "").lower()
        use_parent_child = mode == "parent_child" or is_parent_child_strategy(strategy)
        chunk_size = int(chunking.get("chunk_size", 1000) or 1000)
        chunk_overlap = int(chunking.get("chunk_overlap", 150) or 150)
        parent_chunk_size = int(chunking.get("parent_chunk_size", 1800) or 1800)
        parent_chunk_overlap = int(chunking.get("parent_chunk_overlap", 150) or 150)
        child_chunk_size = int(chunking.get("child_chunk_size", 400) or 400)
        child_chunk_overlap = int(chunking.get("child_chunk_overlap", 80) or 80)
        document_type = (
            config.document_type if hasattr(config, "document_type") else config.get("document_type")
        )

        log.info(
            "chunking_strategy_effective",
            file=str(file_path),
            strategy=strategy,
            mode=mode or None,
            parent_child=use_parent_child,
        )

        global_index = 0
        narrative_blocks = [b for b in blocks if b.block_type != "table"]

        if narrative_blocks:
            chunk_strategy = "page_aware_parent_child" if use_parent_child else strategy
            block_pairs = chunk_blocks(
                narrative_blocks,
                strategy=chunk_strategy,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                parent_chunk_size=parent_chunk_size,
                parent_chunk_overlap=parent_chunk_overlap,
                child_chunk_size=child_chunk_size,
                child_chunk_overlap=child_chunk_overlap,
                document_type=document_type,
                doc_id=config.get("_doc_id"),
            )
            for leaf, block_meta in block_pairs:
                if not leaf.text.strip():
                    continue
                section_path = leaf.section_path or block_meta.get("section_path")
                if isinstance(section_path, list):
                    section_path = " > ".join(section_path)
                yield ParsedRecord(
                    route="qdrant",
                    payload={
                        "page_content": leaf.text,
                        "chunk_index": global_index,
                        "page": None,
                        "chunk_level": "child",
                        "parent_chunk_id": leaf.parent_chunk_id,
                        "parent_content": leaf.parent_text,
                        "parent_index": leaf.parent_index,
                        "child_index_in_parent": leaf.child_index,
                        "section_path": section_path,
                        "parser_version": PARSER_VERSION,
                        "extraction_source": "word",
                        **leaf_metadata_fields(leaf),
                    },
                    text_for_embedding=leaf.text,
                    source_locator={"chunk_index": global_index},
                )
                global_index += 1

        for table_obj in table_objects:
            yield ParsedRecord(
                route="qdrant",
                payload={
                    "page_content": table_obj.markdown,
                    "chunk_index": global_index,
                    "page": None,
                    "section": f"table_{table_obj.table_index}",
                    "extraction_source": "word_table",
                    "has_tables": True,
                    "chunk_level": "table",
                    "parser_version": PARSER_VERSION,
                    **table_obj.to_payload(),
                },
                text_for_embedding=table_obj.to_embed_text(),
                source_locator={"chunk_index": global_index, "table": table_obj.table_index},
            )
            global_index += 1

        if global_index == 0:
            raise ParserError("no_extractable_text", "Word document has no extractable text")

        log.info(
            "word_parse_complete",
            file=str(file_path),
            chunks=global_index,
            tables=len(table_objects),
            parent_child=use_parent_child,
        )
