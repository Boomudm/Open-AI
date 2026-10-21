"""Authoritative cross-encoder reranking + document-diversified selection.

The pipeline relevance signal is the cross-encoder probability — ``sigmoid(logit)``
from ``BAAI/bge-reranker-v2-m3`` — which is an *absolute*, calibrated [0,1] relevance
for the (query, chunk) pair. This replaces the previous within-batch min-max
normalization (which made the "least bad" candidate in an all-irrelevant batch look
perfectly relevant) and the additive cosine-plus-small-bonus scheme (which let the
dense/synthetic base dominate the reranker).

When the cross-encoder model cannot be loaded (e.g. CI without the weights), the
selector degrades to the upstream RRF fusion score, which is itself a calibrated
[0,1] rank-fusion value — never a raw cosine or synthetic lexical number.
"""

from __future__ import annotations

import math
import re
import time
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from spark.core.config import settings
from spark.core.logging import get_logger

log = get_logger(__name__)

_TOKEN_RE = re.compile(r"\w+|[\u0E00-\u0E7F]+", re.UNICODE)


class ChunkLike(Protocol):
    page_content: str
    score: float
    vector_score: float
    payload: dict[str, Any]


@dataclass
class DocGroupScore:
    key: str
    doc_score: float
    chunks: list[Any]


def _tokenize(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text or "")]


def lexical_overlap_score(query: str, doc: str) -> float:
    """BM25-flavored lexical overlap, used as a lexical evidence signal (not for gating)."""
    q_tokens = _tokenize(query)
    d_tokens = _tokenize(doc)
    if not q_tokens or not d_tokens:
        return 0.0
    d_counts = Counter(d_tokens)
    doc_len = max(1, len(d_tokens))
    score = 0.0
    matched = 0
    for t in set(q_tokens):
        tf = d_counts.get(t, 0)
        if tf == 0:
            continue
        matched += 1
        score += (tf / doc_len) * math.log(1 + 1.0 / (1 + tf))
    if matched == 0:
        return 0.0
    if doc_len < 40:
        score *= doc_len / 40
    coverage = matched / max(1, len(set(q_tokens)))
    return score * coverage


def cross_encoder_scores(query: str, doc_texts: Sequence[str]) -> list[float] | None:
    """Absolute cross-encoder relevance in [0,1], or None when the model is unavailable."""
    from spark.retrieval.rerank.cross_encoder import cross_encoder as reranker_service

    return reranker_service.score_pairs(query, doc_texts)


def _authoritative_relevance(query: str, docs: Sequence[Any]) -> tuple[list[float], str]:
    """Return the calibrated [0,1] relevance per doc and the scorer used.

    Primary: cross-encoder probability. Degraded fallback (model unavailable): the
    upstream RRF ``fusion_score`` (or ``score`` for callers that bypass fusion, e.g.
    unit tests building documents directly).
    """
    ce = cross_encoder_scores(query, [d.page_content for d in docs])
    if ce is not None and len(ce) == len(docs):
        return ce, "cross_encoder"
    from spark.core.metrics import reranker_degraded_total

    reranker_degraded_total.labels(reason="rrf_fallback").inc()
    fallback: list[float] = []
    for d in docs:
        fusion = getattr(d, "fusion_score", None)
        fallback.append(float(fusion if fusion is not None else d.score))
    return fallback, "rrf_fusion"


def _doc_group_key(payload: dict[str, Any]) -> str:
    doc_id = payload.get("doc_id")
    if doc_id:
        return str(doc_id)
    source_file = payload.get("source_file")
    if source_file:
        return str(source_file)
    return ""


def _score_document_group(chunks: list[Any]) -> float:
    """Aggregate a document's relevance from its chunk relevances (no type thumb-on-scale)."""
    chunk_scores = sorted((float(c.score) for c in chunks), reverse=True)
    if not chunk_scores:
        return 0.0
    top3 = chunk_scores[:3]
    return min(1.0, 0.6 * chunk_scores[0] + 0.4 * (sum(top3) / len(top3)))


def _preferred_group_tiebreaker(
    group: DocGroupScore,
    *,
    prefer_manual: bool,
    prefer_procedure: bool = False,
) -> int:
    """Product safety routing only (e.g. 'what to do when overheating' must not be
    answered from repair history). A discrete tiebreaker, never a score additive."""
    if not group.chunks:
        return 0
    doc_type = group.chunks[0].payload.get("document_type")
    if prefer_procedure:
        if doc_type == "machine_manual":
            return 3
        if doc_type == "sop":
            return 2
        return 1
    if prefer_manual and doc_type == "machine_manual":
        return 1
    return 0


def _top_chunk_score(group: DocGroupScore) -> float:
    return max((float(c.score) for c in group.chunks), default=0.0)


def cross_document_select(
    query: str,
    docs: Sequence[Any],
    *,
    top_k: int,
    prefer_manual: bool = False,
    prefer_procedure: bool = False,
    max_docs: int | None = None,
    max_chunks_per_doc: int | None = None,
    precomputed_scores: Sequence[float] | None = None,
) -> list[Any]:
    """Score chunks with the authoritative cross-encoder, group by document, and
    return diversified top chunks. ``doc.score`` is overwritten with the calibrated
    relevance so the downstream relevance gate reads an absolute signal."""
    if not docs:
        return []

    max_docs = max_docs if max_docs is not None else settings.rag_max_docs
    max_chunks_per_doc = (
        max_chunks_per_doc if max_chunks_per_doc is not None else settings.rag_max_chunks_per_doc
    )

    docs = list(docs)
    if precomputed_scores is not None and len(precomputed_scores) == len(docs):
        relevances = [float(s) for s in precomputed_scores]
    else:
        relevances, _scorer = _authoritative_relevance(query, docs)
    for doc, rel in zip(docs, relevances, strict=True):
        doc.score = float(min(1.0, max(0.0, rel)))

    groups: dict[str, list[Any]] = defaultdict(list)
    for doc in docs:
        key = _doc_group_key(doc.payload) or f"__chunk_{id(doc)}"
        groups[key].append(doc)

    ranked_groups: list[DocGroupScore] = []
    for key, chunks in groups.items():
        chunks.sort(key=lambda c: c.score, reverse=True)
        ranked_groups.append(
            DocGroupScore(key=key, doc_score=_score_document_group(chunks), chunks=chunks)
        )

    if prefer_procedure:
        ranked_groups.sort(
            key=lambda g: (
                _preferred_group_tiebreaker(
                    g, prefer_manual=prefer_manual, prefer_procedure=prefer_procedure
                ),
                g.doc_score,
                _top_chunk_score(g),
            ),
            reverse=True,
        )
    else:
        ranked_groups.sort(
            key=lambda g: (
                _top_chunk_score(g),
                g.doc_score,
                _preferred_group_tiebreaker(
                    g, prefer_manual=prefer_manual, prefer_procedure=prefer_procedure
                ),
            ),
            reverse=True,
        )

    selected: list[Any] = []
    for group in ranked_groups[:max_docs]:
        selected.extend(group.chunks[:max_chunks_per_doc])

    if prefer_procedure:
        selected.sort(
            key=lambda d: (
                _preferred_group_tiebreaker(
                    DocGroupScore(key="", doc_score=0.0, chunks=[d]),
                    prefer_manual=prefer_manual,
                    prefer_procedure=True,
                ),
                d.score,
            ),
            reverse=True,
        )
    else:
        selected.sort(key=lambda d: d.score, reverse=True)
    return selected[:top_k]


def cross_document_rerank_ms(query: str, docs: Sequence[Any], **kwargs) -> tuple[list[Any], float]:
    """Run cross_document_select and return elapsed milliseconds."""
    start = time.perf_counter()
    result = cross_document_select(query, docs, **kwargs)
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    return result, elapsed_ms
