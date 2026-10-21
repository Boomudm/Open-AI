"""Embedding intent classifier with abstention (Phase 9)."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Callable

from spark.retrieval.intent.types import QueryIntent

_DEFAULT_MODEL = (
    Path(__file__).resolve().parents[4] / "models" / "intent_classifier_v1.json"
)

_CLASSIFIER_INTENTS = {
    "procedure": QueryIntent.PROCEDURE,
    "alarm_diagnostic": QueryIntent.ALARM_DIAGNOSTIC,
    "general": QueryIntent.GENERAL,
}


@dataclass(frozen=True)
class IntentPrediction:
    intent: QueryIntent
    confidence: float
    scores: dict[str, float]


def hash_embed(text: str, *, dim: int = 64) -> list[float]:
    """Deterministic lightweight embed for offline stub / tests."""
    vec = [0.0] * dim
    normalized = (text or "").lower().strip()
    if not normalized:
        return vec
    for word in normalized.split():
        for i, ch in enumerate(word):
            idx = (hash(word) + i * 31 + ord(ch)) % dim
            vec[idx] += 1.0
    for i in range(len(normalized) - 1):
        bigram = normalized[i : i + 2]
        vec[hash(bigram) % dim] += 0.5
    norm = math.sqrt(sum(value * value for value in vec))
    if norm <= 0:
        return vec
    return [value / norm for value in vec]


def _cosine(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        return 0.0
    return sum(x * y for x, y in zip(a, b))


@dataclass
class IntentClassifier:
    """Cosine-similarity classifier over hash or supplied embeddings."""

    abstain_threshold: float
    centroids: dict[str, list[float]]
    embed_fn: Callable[[str], list[float]]

    @classmethod
    def from_json(cls, path: Path | str | None = None) -> IntentClassifier:
        model_path = Path(path) if path else _DEFAULT_MODEL
        raw = json.loads(model_path.read_text(encoding="utf-8"))
        dim = int(raw.get("embed_dim") or 64)
        threshold = float(raw.get("abstain_threshold") or 0.38)
        exemplars: dict[str, list[str]] = raw.get("exemplars") or {}

        def _embed(text: str) -> list[float]:
            return hash_embed(text, dim=dim)

        centroids: dict[str, list[float]] = {}
        for intent, phrases in exemplars.items():
            if not phrases:
                continue
            vectors = [_embed(str(phrase)) for phrase in phrases]
            dim_size = len(vectors[0])
            mean = [0.0] * dim_size
            for vec in vectors:
                for idx, value in enumerate(vec):
                    mean[idx] += value
            count = float(len(vectors))
            mean = [value / count for value in mean]
            norm = math.sqrt(sum(value * value for value in mean))
            centroids[intent] = [value / norm for value in mean] if norm > 0 else mean

        return cls(abstain_threshold=threshold, centroids=centroids, embed_fn=_embed)

    def predict(
        self,
        question: str,
        *,
        embedding: list[float] | None = None,
    ) -> IntentPrediction:
        vector = embedding if embedding is not None else self.embed_fn(question)
        scores = {
            intent: _cosine(vector, centroid)
            for intent, centroid in self.centroids.items()
        }
        if not scores:
            return IntentPrediction(QueryIntent.UNKNOWN, 0.0, {})

        best_label = max(scores, key=scores.get)
        confidence = float(scores[best_label])
        if confidence < self.abstain_threshold:
            return IntentPrediction(QueryIntent.UNKNOWN, confidence, scores)

        mapped = _CLASSIFIER_INTENTS.get(best_label, QueryIntent.GENERAL)
        return IntentPrediction(mapped, confidence, scores)


@lru_cache(maxsize=1)
def get_intent_classifier(model_path: str | None = None) -> IntentClassifier:
    return IntentClassifier.from_json(model_path)
