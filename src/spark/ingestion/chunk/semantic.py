"""Embedding breakpoint semantic chunking (cosine drop between sentences)."""

from __future__ import annotations

import re
from functools import lru_cache

import numpy as np

from spark.core.logging import get_logger
from spark.ingestion.chunking.recursive import recursive_chunk_text

log = get_logger(__name__)

_SENTENCE_SPLIT_RE = re.compile(
    r"(?<=[.!?。])\s+|(?<=\n)\s*(?=\S)|(?<=[\u0E2F\u0E46])\s+"
)


def split_sentences(text: str) -> list[str]:
    if not text.strip():
        return []
    parts = _SENTENCE_SPLIT_RE.split(text.strip())
    return [p.strip() for p in parts if p.strip()]


@lru_cache(maxsize=1)
def _breakpoint_model_name() -> str:
    try:
        from spark.core.llm_profile import load_llm_profile

        profile = load_llm_profile()
        model = profile.get("embedding_model") or profile.get("model")
        return model or "BAAI/bge-m3"
    except Exception:
        return "BAAI/bge-m3"


def _encode_sentences(sentences: list[str]) -> np.ndarray | None:
    if len(sentences) <= 1:
        return None
    try:
        from spark.ingestion.embedder import _load_sentence_transformer

        model = _load_sentence_transformer(_breakpoint_model_name())
        vectors = model.encode(
            sentences,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return np.asarray(vectors)
    except Exception as exc:
        log.debug("semantic_breakpoint_encode_fallback", error=str(exc)[:120])
        return None


def _cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b))


def split_by_embedding_breakpoint(
    text: str,
    *,
    chunk_size: int,
    chunk_overlap: int,
    breakpoint_threshold: float = 0.5,
) -> list[str]:
    """Merge sentences until cosine similarity to next sentence drops below threshold."""
    sentences = split_sentences(text)
    if len(sentences) <= 1:
        return recursive_chunk_text(text, chunk_size=chunk_size, chunk_overlap=chunk_overlap)

    embeddings = _encode_sentences(sentences)
    if embeddings is None:
        return recursive_chunk_text(text, chunk_size=chunk_size, chunk_overlap=chunk_overlap)

    segments: list[str] = []
    current: list[str] = [sentences[0]]
    for i in range(1, len(sentences)):
        sim = _cosine_sim(embeddings[i - 1], embeddings[i])
        if sim < breakpoint_threshold and current:
            segments.append(" ".join(current))
            current = [sentences[i]]
        else:
            current.append(sentences[i])
    if current:
        segments.append(" ".join(current))

    chunks: list[str] = []
    for segment in segments:
        if len(segment) <= chunk_size:
            chunks.append(segment)
        else:
            chunks.extend(
                recursive_chunk_text(segment, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
            )
    return [c for c in chunks if c.strip()]


class EmbeddingBreakpointChunker:
    def __init__(self, *, breakpoint_threshold: float = 0.5) -> None:
        self.breakpoint_threshold = breakpoint_threshold

    def split(self, text: str, *, chunk_size: int, chunk_overlap: int) -> list[str]:
        return split_by_embedding_breakpoint(
            text,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            breakpoint_threshold=self.breakpoint_threshold,
        )
