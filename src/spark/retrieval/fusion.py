"""Single application-layer fusion — vector (Qdrant hybrid) + lexical (Phase 7)."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any, Literal

from spark.retrieval.models import RetrievedDoc

FusionMethod = Literal["rrf", "weighted_rrf", "convex"]
IdentityFn = Callable[[RetrievedDoc], tuple[Any, ...]]

_LEG_SCORE_ATTRS = ("vector_score", "lexical_score", "score")


def _leg_score(doc: RetrievedDoc, list_index: int) -> float:
    if list_index == 0:
        return float(doc.vector_score or doc.score or 0.0)
    if list_index == 1:
        return float(doc.lexical_score or doc.score or 0.0)
    for attr in _LEG_SCORE_ATTRS:
        value = getattr(doc, attr, None)
        if value:
            return float(value)
    return 0.0


def normalize_leg_ranks(
    candidates: list[RetrievedDoc],
    *,
    list_index: int = 0,
) -> list[RetrievedDoc]:
    """Order a single retrieval leg and stamp tie-aware ranks for RRF."""
    if not candidates:
        return []
    ordered = sorted(candidates, key=lambda doc: _leg_score(doc, list_index), reverse=True)
    rank = 1
    for i, doc in enumerate(ordered):
        if i > 0 and _leg_score(ordered[i], list_index) < _leg_score(ordered[i - 1], list_index):
            rank = i + 1
        doc.payload = {**doc.payload, "leg_rank": rank}
    return ordered


def _union_retrieval_modes(target: RetrievedDoc, other: RetrievedDoc) -> None:
    modes: set[str] = set(target.payload.get("retrieval_modes") or [])
    for doc in (target, other):
        mode = doc.payload.get("retrieval_mode")
        if mode:
            modes.add(str(mode))
        for mode in doc.payload.get("retrieval_modes") or []:
            modes.add(str(mode))
    target.payload = {**other.payload, **target.payload}
    if modes:
        target.payload["retrieval_modes"] = sorted(modes)
    if not target.page_content and other.page_content:
        target.page_content = other.page_content


def _list_signal(doc: RetrievedDoc, list_index: int) -> float:
    if list_index == 0:
        return float(doc.vector_score or doc.score or 0.0)
    if list_index == 1:
        return float(doc.lexical_score or doc.score or 0.0)
    return float(doc.score or doc.vector_score or doc.lexical_score or 0.0)


def _normalize_weights(weights: Sequence[float], list_count: int) -> list[float]:
    if list_count <= 0:
        return []
    if not weights:
        return [1.0] * list_count
    padded = list(weights[:list_count])
    if len(padded) < list_count:
        padded.extend([1.0] * (list_count - len(padded)))
    total = sum(padded)
    if total <= 0:
        return [1.0 / list_count] * list_count
    return [w / total for w in padded]


def _fuse_rrf(
    lists: list[list[RetrievedDoc]],
    *,
    k: int,
    weights: list[float],
    weighted: bool,
    identity_fn: IdentityFn,
    expected_leg_count: int = 2,
) -> list[RetrievedDoc]:
    if k < 1:
        raise ValueError("rrf k must be >= 1")

    per_list_max = 1.0 / (k + 1)
    norm = per_list_max * expected_leg_count
    fused: dict[tuple[Any, ...], RetrievedDoc] = {}
    raw_scores: dict[tuple[Any, ...], float] = {}

    for list_idx, group in enumerate(lists):
        weight = weights[list_idx] if weighted else 1.0
        for rank, doc in enumerate(group, start=1):
            key = identity_fn(doc)
            contribution = weight * (1.0 / (k + rank))
            existing = fused.get(key)
            if existing is None:
                fused[key] = doc
                raw_scores[key] = contribution
            else:
                raw_scores[key] += contribution
                if doc.vector_score > existing.vector_score:
                    existing.vector_score = doc.vector_score
                if doc.lexical_score > existing.lexical_score:
                    existing.lexical_score = doc.lexical_score
                _union_retrieval_modes(existing, doc)

    for key, doc in fused.items():
        normalized = raw_scores[key] / norm if norm > 0 else 0.0
        normalized = min(1.0, max(0.0, normalized))
        doc.fusion_score = normalized
        doc.score = normalized

    return sorted(fused.values(), key=lambda d: d.fusion_score or 0.0, reverse=True)


def _fuse_convex(
    lists: list[list[RetrievedDoc]],
    *,
    weights: list[float],
    identity_fn: IdentityFn,
) -> list[RetrievedDoc]:
    fused: dict[tuple[Any, ...], RetrievedDoc] = {}
    raw_scores: dict[tuple[Any, ...], float] = {}

    for list_idx, group in enumerate(lists):
        if not group:
            continue
        weight = weights[list_idx]
        peak = max(_list_signal(doc, list_idx) for doc in group)
        peak = peak if peak > 0 else 1.0
        for doc in group:
            key = identity_fn(doc)
            contribution = weight * (_list_signal(doc, list_idx) / peak)
            existing = fused.get(key)
            if existing is None:
                fused[key] = doc
                raw_scores[key] = contribution
            else:
                raw_scores[key] += contribution
                if doc.vector_score > existing.vector_score:
                    existing.vector_score = doc.vector_score
                if doc.lexical_score > existing.lexical_score:
                    existing.lexical_score = doc.lexical_score
                _union_retrieval_modes(existing, doc)

    for key, doc in fused.items():
        normalized = min(1.0, max(0.0, raw_scores[key]))
        doc.fusion_score = normalized
        doc.score = normalized

    return sorted(fused.values(), key=lambda d: d.fusion_score or 0.0, reverse=True)


def fuse_two_lists(
    vector_hits: list[RetrievedDoc],
    lexical_hits: list[RetrievedDoc],
    *,
    weights: tuple[float, float],
    method: FusionMethod = "weighted_rrf",
    rrf_k: int = 60,
    identity_fn: IdentityFn,
) -> list[RetrievedDoc]:
    """Fuse Qdrant hybrid list + lexical list — single application fusion point."""
    return fuse_candidates(
        [vector_hits, lexical_hits],
        method=method,
        weights=list(weights),
        rrf_k=rrf_k,
        identity_fn=identity_fn,
    )


def fuse_candidates(
    lists: Sequence[Sequence[RetrievedDoc]],
    *,
    method: FusionMethod = "rrf",
    weights: Sequence[float] | None = None,
    rrf_k: int = 60,
    identity_fn: IdentityFn,
) -> list[RetrievedDoc]:
    normalized_lists = [
        normalize_leg_ranks(list(group), list_index=idx)
        for idx, group in enumerate(lists)
        if group
    ]
    if not normalized_lists:
        return []

    resolved_weights = _normalize_weights(weights or (), len(normalized_lists))

    if method == "convex":
        return _fuse_convex(normalized_lists, weights=resolved_weights, identity_fn=identity_fn)
    if method == "weighted_rrf":
        return _fuse_rrf(
            normalized_lists,
            k=rrf_k,
            weights=resolved_weights,
            weighted=True,
            identity_fn=identity_fn,
        )
    return _fuse_rrf(
        normalized_lists,
        k=rrf_k,
        weights=resolved_weights,
        weighted=False,
        identity_fn=identity_fn,
    )


def reciprocal_rank_fusion(
    result_lists: Sequence[Sequence[RetrievedDoc]],
    *,
    k: int,
    identity_fn: IdentityFn,
) -> list[RetrievedDoc]:
    """Fuse ranked retriever outputs — preserves caller list order (no re-sort)."""
    if k < 1:
        raise ValueError("rrf k must be >= 1")
    lists = [list(group) for group in result_lists if group]
    if not lists:
        return []

    per_list_max = 1.0 / (k + 1)
    norm = per_list_max * len(lists)

    fused: dict[tuple[Any, ...], RetrievedDoc] = {}
    raw_scores: dict[tuple[Any, ...], float] = {}

    for group in lists:
        for rank, doc in enumerate(group, start=1):
            key = identity_fn(doc)
            contribution = 1.0 / (k + rank)
            existing = fused.get(key)
            if existing is None:
                fused[key] = doc
                raw_scores[key] = contribution
            else:
                raw_scores[key] += contribution
                if doc.vector_score > existing.vector_score:
                    existing.vector_score = doc.vector_score
                if doc.lexical_score > existing.lexical_score:
                    existing.lexical_score = doc.lexical_score
                _union_retrieval_modes(existing, doc)

    for key, doc in fused.items():
        normalized = raw_scores[key] / norm if norm > 0 else 0.0
        normalized = min(1.0, max(0.0, normalized))
        doc.fusion_score = normalized
        doc.score = normalized

    return sorted(fused.values(), key=lambda d: d.fusion_score or 0.0, reverse=True)
