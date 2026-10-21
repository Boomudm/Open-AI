"""Span-level evidence selection with offsets (Phase 10)."""

from __future__ import annotations

import re
from dataclasses import dataclass

from spark.retrieval.models import RetrievedDoc
from spark.generation.parent_context import doc_chunk_id
from spark.retrieval.scoring import (
    _doc_evidence_score,
    _docs_for_symptom_action_evidence,
    _is_symptom_action_query,
    _procedure_doc_rank,
)
from spark.retrieval.synthesis import (
    _collapse_horizontal_whitespace,
    _evidence_snippets_for_doc,
    _trim_evidence_text,
)


@dataclass(frozen=True)
class EvidenceSpan:
    chunk_id: str
    text: str
    doc: RetrievedDoc
    score: float
    start_offset: int = 0
    end_offset: int = 0

    def as_source_span(self) -> dict[str, int | str]:
        return {
            "chunk_id": self.chunk_id,
            "start_offset": self.start_offset,
            "end_offset": self.end_offset,
            "text": self.text[:240],
        }


def _find_span_offsets(snippet: str, page_content: str) -> tuple[int, int]:
    body = page_content or ""
    snippet = (snippet or "").strip()
    if not snippet or not body:
        return 0, 0
    for candidate in (snippet, re.sub(r"\s+", " ", snippet)):
        idx = body.find(candidate)
        if idx < 0:
            idx = body.lower().find(candidate.lower())
        if idx >= 0:
            return idx, idx + len(candidate)
    return 0, min(len(body), len(snippet))


def select_evidence_spans(
    question: str,
    docs: list[RetrievedDoc],
    *,
    max_spans: int = 3,
) -> list[EvidenceSpan]:
    docs_with_ids = [d for d in docs if doc_chunk_id(d)]
    if not docs_with_ids:
        return []

    ranked_docs = sorted(
        _docs_for_symptom_action_evidence(question, docs_with_ids),
        key=lambda d: (
            _procedure_doc_rank(d) if _is_symptom_action_query(question) else 0,
            _doc_evidence_score(question, d),
            d.score,
        ),
        reverse=True,
    )

    spans: list[EvidenceSpan] = []
    seen: set[tuple[str, str]] = set()
    for doc in ranked_docs:
        chunk_id = doc_chunk_id(doc)
        if not chunk_id:
            continue
        for snippet, score in _evidence_snippets_for_doc(question, doc):
            key = (chunk_id.lower(), snippet.strip().lower())
            if key in seen:
                continue
            seen.add(key)
            start, end = _find_span_offsets(snippet, doc.page_content or "")
            spans.append(
                EvidenceSpan(
                    chunk_id=chunk_id,
                    text=snippet.strip(),
                    doc=doc,
                    score=float(score),
                    start_offset=start,
                    end_offset=end,
                )
            )
            if len(spans) >= max_spans:
                return sorted(spans, key=lambda s: s.score, reverse=True)

    if not spans and ranked_docs:
        top = ranked_docs[0]
        chunk_id = doc_chunk_id(top)
        excerpt = _trim_evidence_text(top.page_content)
        if chunk_id and excerpt:
            start, end = _find_span_offsets(excerpt, top.page_content or "")
            spans.append(
                EvidenceSpan(
                    chunk_id=chunk_id,
                    text=excerpt,
                    doc=top,
                    score=max(_doc_evidence_score(question, top), top.score, 0.1),
                    start_offset=start,
                    end_offset=end,
                )
            )
    return sorted(spans, key=lambda s: s.score, reverse=True)


def _span_text_in_doc(span_text: str, page_content: str) -> bool:
    snippet = (span_text or "").strip()
    body = page_content or ""
    if not snippet or not body:
        return False
    if snippet.endswith(("…", "...")):
        snippet = snippet.rstrip(".…").rstrip()
    if snippet in body or snippet.lower() in body.lower():
        return True
    normalized_snippet = re.sub(r"\s+", " ", snippet)
    normalized_body = re.sub(r"\s+", " ", body.strip())
    return (
        normalized_snippet in normalized_body
        or normalized_snippet.lower() in normalized_body.lower()
    )


def validate_spans_grounded(spans: list[EvidenceSpan], docs: list[RetrievedDoc]) -> list[EvidenceSpan]:
    id_map = {doc_chunk_id(d).lower(): d for d in docs if doc_chunk_id(d)}
    validated: list[EvidenceSpan] = []
    for span in spans:
        doc = id_map.get(span.chunk_id.lower())
        if doc is None:
            continue
        if _span_text_in_doc(span.text, doc.page_content or ""):
            validated.append(span)
    return validated


def spans_cover_question(spans: list[EvidenceSpan], *, min_spans: int = 1) -> bool:
    return len(spans) >= min_spans


def spans_partial(spans: list[EvidenceSpan]) -> bool:
    return 0 < len(spans) < 2


def spans_need_translation(question: str, spans: list[EvidenceSpan]) -> bool:
    from spark.generation.thai_enforce import question_prefers_thai_output
    from spark.retrieval.synthesis import _thai_ratio

    if not question_prefers_thai_output(question):
        return False
    return any(_thai_ratio(span.text) < 0.12 for span in spans)


def format_extractive_with_citations(spans: list[EvidenceSpan]) -> tuple[str, list[RetrievedDoc]]:
    if not spans:
        return "", []
    lines = ["พบข้อมูลที่เกี่ยวข้องจากเอกสาร:"]
    used_docs: list[RetrievedDoc] = []
    seen_docs: set[str] = set()
    seen_span_keys: set[tuple[str, str]] = set()
    for span in spans:
        # Collapse spaces/tabs only — keep line breaks so multi-row markdown
        # tables (extracted from PDF spec tables) stay readable instead of
        # becoming one unbroken line of "|" characters (chat UI renders them
        # as tables; see SparkMessageContent.tsx).
        body = _collapse_horizontal_whitespace((span.text or "").strip()).rstrip(".")
        if not body:
            continue
        span_key = (span.chunk_id.lower(), body[:120].lower())
        if span_key in seen_span_keys:
            continue
        seen_span_keys.add(span_key)
        if "\n" in body:
            # Multi-line evidence (a markdown table extracted from a PDF spec
            # sheet) — keep it as its own block instead of forcing it into a
            # single prose bullet; the chat UI renders "| ... |" blocks as
            # tables (see SparkMessageContent.tsx). The chunk_id marker gets
            # its own line so it doesn't read as part of the last table row.
            lines.append(body)
            lines.append(f"[chunk_id:{span.chunk_id}]")
        else:
            lines.append(f"- {body} [chunk_id:{span.chunk_id}].")
        key = span.chunk_id.lower()
        if key not in seen_docs:
            seen_docs.add(key)
            used_docs.append(span.doc)
    if not used_docs:
        return "", []
    lines.append("สรุปนี้ยึดตามข้อความที่พบในเอกสารเท่านั้น")
    return "\n".join(lines), used_docs
