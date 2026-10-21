"""Exact evidence recovery for high-signal factory terms."""

from __future__ import annotations

import re
from collections.abc import Iterable

from sqlalchemy import case, literal, or_, select

from spark.core.config import settings
from spark.core.database import AsyncSessionLocal
from spark.db.models.docs import Document, DocumentChunk
from spark.retrieval.intent.types import IntentPlan, QueryIntent
from spark.retrieval.lexical.runtime import chunk_to_retrieved
from spark.retrieval.lexical.scope import scope_filters
from spark.retrieval.lexical.tokenize_industrial import (
    extract_industrial_tokens,
    extract_plc_tags,
    extract_symbolic_names,
)
from spark.retrieval.models import RAGFilter, RetrievedDoc

_MACHINE_SCOPE_RE = re.compile(r"^(?:MC|MX|MCH|LINE)[-_]?\d+$", re.IGNORECASE)
_PURE_NUMBER_RE = re.compile(r"^\d+(?:\.\d+)?$")
# "X1 ขา 5" / "X1 เทอร์มินอล 5" / "X1 pin 5" → the "X1:5" form the vision
# connection tables actually print, so a spoken-style terminal question
# exact-matches the table row. The terminal side stays short and alphanumeric
# so prose after the keyword ("ขา 5 ไปไหน" → "5") can't drag words in.
_TERMINAL_PHRASE_RE = re.compile(
    r"\b([A-Za-z]{1,6}\d{1,4})\s*(?:ขา|ขั้ว|เทอร์มินอล|เทอมินอล|terminal|pin)\s*"
    r"([A-Za-z0-9+\-]{1,10})\b",
    re.IGNORECASE,
)


def _terminal_ref_variants(question: str) -> list[str]:
    return [
        f"{m.group(1).upper()}:{m.group(2).upper()}"
        for m in _TERMINAL_PHRASE_RE.finditer(question or "")
    ]


def _escape_like(term: str) -> str:
    return (
        term.replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
    )


def _append_unique(target: list[str], terms: Iterable[str]) -> None:
    seen = {term.casefold() for term in target}
    for raw in terms:
        term = str(raw or "").strip()
        if len(term) < 2:
            continue
        key = term.casefold()
        if key in seen:
            continue
        target.append(term)
        seen.add(key)


def _is_exact_safe_token(token: str) -> bool:
    normalized = token.strip()
    if len(normalized) < 2:
        return False
    if _MACHINE_SCOPE_RE.fullmatch(normalized):
        return False
    if _PURE_NUMBER_RE.fullmatch(normalized):
        return False
    return any(ch.isdigit() or ch in "._-" for ch in normalized) or "_" in normalized


def exact_evidence_terms(question: str, plan: IntentPlan | None = None) -> list[str]:
    """Extract terms worth querying as literal evidence in Postgres."""
    raw = question or ""
    lower = raw.lower()
    terms: list[str] = []

    _append_unique(terms, extract_plc_tags(raw))
    _append_unique(terms, extract_symbolic_names(raw))
    _append_unique(terms, _terminal_ref_variants(raw))
    _append_unique(
        terms,
        (
            token
            for token in extract_industrial_tokens(raw, limit=40)
            if _is_exact_safe_token(token)
        ),
    )

    if "interface board" in lower:
        _append_unique(terms, ["interface board", "TORX", "screw"])
    if "kr c5" in lower or "krc5" in lower:
        _append_unique(terms, ["KR C5 micro"])
    if any(word in raw for word in ("สายเคเบิล", "ตู้คอนโทรล", "ตู้ควบคุม", "หุ่นยนต์")) or "cable" in lower:
        _append_unique(
            terms,
            [
                "connecting cables",
                "connecting cable set",
                "cable length",
                "motor cable",
                "data cable",
                "robot controller",
            ],
        )
    if any(word in raw for word in ("สกรู", "ขัน")):
        _append_unique(terms, ["screw", "screws", "TORX"])
    if any(word in raw for word in ("รีเซ็ต", "reset")) and "alarm" in lower:
        _append_unique(terms, ["ALM-RST", "Alarm reset", "reset the alarm"])
    if "non-excitation" in lower:
        _append_unique(terms, ["Non-excitation"])
    if "excitation" in lower:
        _append_unique(terms, ["Excitation", "Motor excitation"])

    drawingish = plan and plan.intent == QueryIntent.DRAWING
    if drawingish or "แบบไฟฟ้า" in raw or "wiring" in lower or "diagram" in lower:
        if "air valve" in lower or "วาล์วลม" in raw:
            _append_unique(terms, ["Air Valve"])
        if "water valve" in lower or "วาล์วน้ำ" in raw:
            _append_unique(terms, ["Water Valve"])
        if "vacuum" in lower or "สูญญากาศ" in raw:
            _append_unique(terms, ["Vacuum Gen", "Vacuum Generator"])
        if "disk" in lower or "disc" in lower:
            _append_unique(terms, ["Disk"])
        if "spd" in lower:
            _append_unique(terms, ["SPD-CTRL", "SPD_CTRL"])

    return terms[:40]


_TOPICAL_LATIN_WORD_RE = re.compile(r"[A-Za-z]{3,}")
_MAX_TOPICAL_RANK_TERMS = 8


def _topical_rank_terms(question: str, exact_terms: list[str]) -> list[str]:
    """Latin words the user typed that aren't already exact-match predicates."""
    from spark.retrieval.scoring import _GENERIC_LATIN_QUERY_TERMS

    already = {part.casefold() for term in exact_terms for part in term.split()}
    out: list[str] = []
    seen: set[str] = set()
    for word in _TOPICAL_LATIN_WORD_RE.findall(question or ""):
        key = word.casefold()
        if key in seen or key in already or key in _GENERIC_LATIN_QUERY_TERMS:
            continue
        out.append(word)
        seen.add(key)
        if len(out) >= _MAX_TOPICAL_RANK_TERMS:
            break
    return out


def _exact_limit(question: str, plan: IntentPlan | None, top_k: int) -> int:
    base = max(top_k * int(settings.rag_retrieve_multiplier or 1), 12)
    lower = (question or "").lower()
    if plan and plan.intent == QueryIntent.IO_MAPPING:
        if any(marker in lower for marker in ("not mapped", "no symbolic", "symbolic link", "map")):
            return max(base, 40)
        return max(base, 24)
    if plan and plan.intent == QueryIntent.DRAWING:
        return max(base, 24)
    return max(base, 16)


async def retrieve_exact_evidence_candidates(
    query: str,
    rf: RAGFilter,
    top_k: int,
    *,
    plan: IntentPlan | None = None,
    allowed_doc_ids: list[str] | None = None,
) -> list[RetrievedDoc]:
    terms = exact_evidence_terms(query, plan)
    if not terms:
        return []

    scope = scope_filters(rf, allowed_doc_ids)
    if scope is None:
        return []

    content = DocumentChunk.content
    predicates = [
        content.ilike(f"%{_escape_like(term)}%", escape="\\")
        for term in terms
    ]
    rank_expr = literal(0.0)
    for term, predicate in zip(terms, predicates, strict=False):
        weight = 2.0 if any(ch in term for ch in "._-") else 1.0
        rank_expr = rank_expr + case((predicate, literal(weight)), else_=literal(0.0))

    # Rank-only topical co-occurrence: a model-name term ("KR C5 micro") matches
    # the running header/footer/index of every page of that manual, and the
    # created_at tiebreak then surfaces arbitrary chunks (index pages) ahead of
    # the section that answers the question. The Latin words the user typed
    # alongside ("safe input", "voltage") discriminate the right section —
    # reward chunks that also contain them, without widening the candidate set.
    for topical in _topical_rank_terms(query, terms):
        rank_expr = rank_expr + case(
            (content.ilike(f"%{_escape_like(topical)}%", escape="\\"), literal(1.5)),
            else_=literal(0.0),
        )

    lower = (query or "").lower()
    if any(marker in lower for marker in ("not mapped", "no symbolic", "symbolic link", "map")):
        rank_expr = rank_expr + case(
            (content.ilike("%No symbolic link mapped%"), literal(3.0)),
            else_=literal(0.0),
        )
    if any(marker in lower for marker in ("เชื่อม", "ต่อกับ", "connect", "modbus", "register")):
        rank_expr = rank_expr + case(
            (content.ilike("%connects to%"), literal(2.0)),
            else_=literal(0.0),
        )

    stmt = (
        select(DocumentChunk, Document, rank_expr.label("exact_rank"))
        .join(Document, Document.doc_id == DocumentChunk.doc_id)
        .where(*scope, or_(*predicates))
        .order_by(rank_expr.desc(), DocumentChunk.created_at.desc())
        .limit(_exact_limit(query, plan, top_k))
    )

    candidates: list[RetrievedDoc] = []
    async with AsyncSessionLocal() as session:
        rows = (await session.execute(stmt)).all()
    for row in rows:
        chunk, document = row[0], row[1]
        rank = float(row[2] or 0.0)
        doc = chunk_to_retrieved(
            query,
            chunk,
            document,
            retrieval_mode="exact_evidence",
            db_rank=max(rank, 1.0),
        )
        if doc is None:
            continue
        doc.score = max(doc.score, min(1.0, 0.55 + rank / 20.0))
        doc.lexical_score = max(doc.lexical_score, doc.score)
        doc.payload["exact_terms"] = terms
        candidates.append(doc)
    return candidates
