# -*- coding: utf-8 -*-
"""Ask-the-user-back when a question is ambiguous.

Two cases (feature request 2026-07-07):
  (a) No machine is locked and the retrieved evidence straddles several machines
      with comparable relevance — ask which machine is meant instead of guessing.
  (b) The question is too vague to retrieve against (very short, no entity, no
      prior turn to inherit context from) — ask for detail instead of returning
      a misleading "no data".
Both keep the answer correct-by-abstention: we never fabricate scope.
"""

from __future__ import annotations

import re
from collections import Counter

from spark.core.logging import get_logger
from spark.retrieval.models import RAGFilter

log = get_logger(__name__)

# A question is "self-sufficient" (not vague) if it names a machine/part code, an
# alarm/hex code, or is reasonably long. Bare fragments with none of these and no
# prior turn cannot be retrieved meaningfully.
_CODE_RE = re.compile(r"[A-Za-z]{1,4}-?\d{2,5}|\b[0-9A-Fa-f]{2,4}h\b")
_MIN_SELF_SUFFICIENT_CHARS = 12


def is_vague_question(question: str, *, has_prior_user: bool) -> bool:
    q = (question or "").strip()
    if has_prior_user:
        return False  # a follow-up inherits context from the prior turn
    if _CODE_RE.search(q):
        return False
    return len(q) < _MIN_SELF_SUFFICIENT_CHARS


async def candidate_machines(
    question: str,
    *,
    factory_id: str | None,
    embedder,
    min_score: float = 0.42,
    probe_k: int = 15,
    min_hits_per_machine: int = 2,
) -> list[str]:
    """Return distinct machine_ids whose chunks match the query strongly.

    Returns 2+ ids only when the evidence genuinely straddles machines — a
    single stray cross-machine hit does not trigger a clarification.
    """
    from spark.core.qdrant import ensure_collection, get_async_qdrant_client
    from spark.retrieval.vector.qdrant_search import search_qdrant_hybrid

    rf = RAGFilter(factory_id=factory_id)  # deliberately no machine scope
    try:
        result = await search_qdrant_hybrid(
            query=question,
            rf=rf,
            top_k=probe_k,
            embedder=embedder,
            get_client=get_async_qdrant_client,
            ensure_collection=ensure_collection,
        )
    except Exception as exc:  # probe must never break the answer path
        log.warning("clarify_probe_failed", error=str(exc)[:200])
        return []

    strong = Counter()
    for hit in getattr(result, "hits", []) or []:
        score = float(getattr(hit, "score", 0.0) or 0.0)
        mid = str((hit.payload or {}).get("machine_id") or "").strip()
        if mid and score >= min_score:
            strong[mid] += 1
    machines = [mid for mid, n in strong.items() if n >= min_hits_per_machine]
    return sorted(machines)


def clarify_machine_message(machines: list[str], names: dict[str, str] | None = None) -> str:
    names = names or {}
    listed = "\n".join(
        f"- {mid}" + (f" ({names[mid]})" if names.get(mid) else "")
        for mid in machines
    )
    return (
        "พบข้อมูลที่เกี่ยวข้องในหลายเครื่องจักรครับ "
        "กรุณาระบุว่าต้องการทราบข้อมูลของเครื่องจักรใด:\n"
        f"{listed}\n\n"
        "ตอบกลับด้วยรหัสเครื่อง (เช่น " + machines[0] + ") แล้ว Neo จะค้นหาให้เฉพาะเครื่องนั้นครับ"
    )


VAGUE_MESSAGE = (
    "คำถามยังไม่ชัดเจนพอสำหรับการค้นหาครับ "
    "กรุณาระบุรายละเอียดเพิ่มเติม เช่น ชื่อ/รหัสเครื่องจักร รหัส alarm "
    "หรือหัวข้อที่ต้องการทราบ แล้ว Neo จะช่วยค้นหาให้ครับ"
)
