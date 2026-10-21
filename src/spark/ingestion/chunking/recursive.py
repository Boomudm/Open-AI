"""Shared recursive text splitting for chunking strategies."""

from __future__ import annotations

from typing import Any

from langchain.text_splitter import RecursiveCharacterTextSplitter


def recursive_chunk_text(
    text: str, *, chunk_size: int, chunk_overlap: int, token_counter: Any | None = None
) -> list[str]:
    if not text:
        return []
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", "。", ".", " ", ""],
        length_function=token_counter if token_counter is not None else len,
    )
    return splitter.split_text(text)
