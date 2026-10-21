"""Chat routing helpers for external Postgres Text-to-SQL.

Runs an external data source's Text-to-SQL only when the factory has an enabled
source configured AND the question (or at least one part of a compound
question) looks like aggregate/temporal analytics.

Compound handling: a question like "เดือนนี้ MC-777 ซ่อมกี่ครั้ง และ safe input
แรงดันเท่าไหร่" used to be sent WHOLE to the SQL generator — the LLM dropped
the time filter and the document half was silently ignored. Now each part is
routed on its own: analytic parts each get their own SQL run (so per-part
filters survive), and document parts come back as ``residual_question`` for the
caller to answer through the RAG pipelines and merge.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from spark.services.intent_classifier import QuestionRouting


def _is_analytic(part: str) -> bool:
    from spark.services.analytic_signals import has_aggregate_signal, has_analytic_signal

    q = part.casefold()
    return has_analytic_signal(q) or has_aggregate_signal(q)


def _mask_identifiers(text: str, idents: list[str]) -> str:
    """Blank out machine/part ids before temporal matching — the digits in
    "MC-777 เดือนนี้" otherwise match the N-unit window pattern as "777 เดือน"."""
    for ident in idents:
        text = text.replace(ident, " ")
    return text


def _carry_context(part: str, idents: list[str], temporal: str | None) -> str:
    """Attach context a clause lost in the split.

    "MC-777 เดือนนี้ซ่อมกี่ครั้ง และค่าใช้จ่ายรวมเท่าไหร่" splits into a second
    clause with neither the machine id nor the time window — without carrying
    both, its SQL aggregates factory-wide and all-time (observed live: 64,000
    all-time instead of 52,000 this month)."""
    from spark.retrieval.preprocess.compound import question_identifiers
    from spark.services.analytic_signals import TEMPORAL_ANALYTIC_RE

    additions: list[str] = []
    if idents and not question_identifiers(part):
        additions.append(f"ของ {' '.join(idents[:2])}")
    if temporal and not TEMPORAL_ANALYTIC_RE.search(_mask_identifiers(part, idents)):
        additions.append(temporal)
    if not additions:
        return part
    return f"{part} ({' '.join(additions)})"


def compound_prefix_text(external_result: dict[str, Any]) -> str:
    """Rendered SQL sections + the residual question's header.

    Prepended to the RAG answer for the document part, so the streamed tokens
    and the persisted merged answer read the same.
    """
    sections = list(external_result.get("sql_sections") or [])
    residual = str(external_result.get("residual_question") or "")
    lines: list[str] = []
    n = 0
    for sec in sections:
        n += 1
        lines.append(f"**{n}) {sec['question']}**")
        lines.append(str(sec.get("answer") or "").strip())
        lines.append("")
    if residual:
        n += 1
        lines.append(f"**{n}) {residual}**")
    return "\n".join(lines).strip() + "\n"


def merge_compound_answer(external_result: dict[str, Any], rag_answer: str) -> str:
    return f"{compound_prefix_text(external_result)}{(rag_answer or '').strip()}"


async def try_external_analytics(
    session: AsyncSession,
    question: str,
    routing: QuestionRouting,
    *,
    factory_id: str | None,
    job_position_ids: list[str] | None = None,
) -> dict[str, Any] | None:
    """Run external SQL when factory has an enabled source and the question
    (or a compound part of it) is analytic.

    Returns None when nothing analytic should run. Otherwise a result dict in
    the usual external-analytics shape; for compound questions it additionally
    carries ``sql_sections`` (one entry per analytic part) and, when document
    parts remain, ``residual_question`` for the caller to answer via RAG.
    """
    import asyncio

    from spark.retrieval.preprocess.compound import (
        question_identifiers,
        split_compound_question,
    )
    from spark.services.data_source_service import resolve_external_source_for_factory
    from spark.services.external_analytics_service import external_analytics_service
    from spark.services.external_sql.constants import REASON_OK

    if not factory_id:
        return None
    bundle = await resolve_external_source_for_factory(
        session, factory_id, job_position_ids=job_position_ids
    )
    if bundle is None or not bundle.has_tables:
        return None

    parts = split_compound_question(question)

    if len(parts) <= 1:
        if getattr(routing, "route", "rag") != "sql" and not _is_analytic(question):
            return None
        return await external_analytics_service.query(
            question,
            bundle.source,
            factory_id=factory_id,
            tables=bundle.visible_tables,
        )

    from spark.services.analytic_signals import TEMPORAL_ANALYTIC_RE

    idents = question_identifiers(question)
    temporal_match = TEMPORAL_ANALYTIC_RE.search(_mask_identifiers(question, idents))
    temporal = temporal_match.group(0) if temporal_match else None
    sql_parts: list[str] = []
    doc_parts: list[str] = []
    for part in parts:
        if _is_analytic(part):
            # Context carry-over is for SQL aggregation scope only; the RAG
            # side has its own contextualization, and pinning a machine id
            # onto an unrelated document clause skews retrieval.
            sql_parts.append(_carry_context(part, idents, temporal))
        else:
            doc_parts.append(part)
    if not sql_parts:
        return None

    results = await asyncio.gather(
        *(
            external_analytics_service.query(
                p,
                bundle.source,
                factory_id=factory_id,
                tables=bundle.visible_tables,
            )
            for p in sql_parts
        )
    )

    sections = [
        {
            "question": p,
            "answer": r.get("answer"),
            "sql": r.get("sql"),
            "row_count": r.get("row_count"),
            "reason_code": r.get("reason_code"),
        }
        for p, r in zip(sql_parts, results)
    ]
    all_ok = all(r.get("reason_code") == REASON_OK for r in results)
    first = results[0]

    if doc_parts:
        combined_answer = ""  # caller merges via merge_compound_answer()
        residual = " และ ".join(doc_parts)
    elif len(sections) == 1:
        combined_answer = str(first.get("answer") or "")
        residual = None
    else:
        combined_answer = "\n".join(
            f"**{i + 1}) {s['question']}**\n{str(s['answer'] or '').strip()}\n"
            for i, s in enumerate(sections)
        ).strip()
        residual = None

    out: dict[str, Any] = {
        "answer": combined_answer,
        "sql": "; ".join(str(s.get("sql") or "") for s in sections if s.get("sql")),
        "rows": list(first.get("rows") or []),
        "row_count": sum(int(s.get("row_count") or 0) for s in sections),
        "reason_code": REASON_OK if all_ok else next(
            (str(r.get("reason_code")) for r in results if r.get("reason_code") != REASON_OK),
            REASON_OK,
        ),
        "sql_generation_path": "external_llm_sql",
        "pipeline": "external_sql",
        "data_source_id": first.get("data_source_id"),
        "data_source_name": first.get("data_source_name"),
        "sql_sections": sections,
    }
    if residual:
        out["residual_question"] = residual
    return out
