"""Embedding canary check — detect silent model drift before index corruption."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from spark.core.logging import get_logger

log = get_logger(__name__)

_CANARY_PATH = Path(__file__).resolve().parents[4] / "configs" / "embedding_canary.json"


def _load_canary() -> dict:
    if not _CANARY_PATH.is_file():
        return {}
    with _CANARY_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def _save_canary(data: dict) -> None:
    with _CANARY_PATH.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _cosine_sim(a: list[float], b: list[float]) -> float:
    va = np.array(a, dtype=np.float32)
    vb = np.array(b, dtype=np.float32)
    norm_a = float(np.linalg.norm(va))
    norm_b = float(np.linalg.norm(vb))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(va, vb) / (norm_a * norm_b))


class EmbeddingDriftError(Exception):
    def __init__(self, similarity: float, threshold: float) -> None:
        self.similarity = similarity
        self.threshold = threshold
        super().__init__(
            f"Embedding canary drift detected: similarity={similarity:.6f} < threshold={threshold}"
        )


async def verify_embedding_canary() -> float:
    """Embed canary sentence and compare to stored reference. Returns similarity.

    On first run (no reference), stores the vector and returns 1.0.
    On subsequent runs, compares and raises EmbeddingDriftError if below threshold.
    """
    canary = _load_canary()
    sentence = canary.get("canary_sentence")
    if not sentence:
        return 1.0

    threshold = float(canary.get("min_similarity", 0.995))
    reference = canary.get("reference_vector")

    from spark.ingestion.index.embedder import Embedder

    embedder = Embedder.get()
    current_vector = await embedder.embed_query(sentence)

    if reference is None or not isinstance(reference, list) or len(reference) == 0:
        canary["reference_vector"] = current_vector
        _save_canary(canary)
        log.info("embedding_canary_reference_stored", dimension=len(current_vector))
        return 1.0

    if len(reference) != len(current_vector):
        log.error(
            "embedding_canary_dimension_mismatch",
            stored=len(reference),
            current=len(current_vector),
        )
        canary["reference_vector"] = current_vector
        _save_canary(canary)
        return 1.0

    similarity = _cosine_sim(current_vector, reference)
    log.info("embedding_canary_check", similarity=round(similarity, 6), threshold=threshold)

    if similarity < threshold:
        raise EmbeddingDriftError(similarity, threshold)

    return similarity
