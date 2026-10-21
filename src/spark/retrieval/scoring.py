from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from typing import Any

from .common import log
from .constants import MIN_EVIDENCE_SCORE
from .models import RAGFilter, RetrievedDoc
from .tuning import RagTuningContext

_MANUAL_INTENT = (
    "ร้อน", "overheat", "temperature", "อุณหภูมิ", "heat", "cooling", "พัดลม", "fan",
    "คู่มือ", "manual", "ความปลอดภัย", "safety", "warning", "caution", "install",
    "ติดตั้ง", "procedure", "วิธี", "bearing", "maintenance schedule", "servo",
    "ลูกปืน", "แรงดัน", "สั่น", "เสียงดัง", "รั่ว", "หล่อลื่น", "สายพาน",
    "ปั๊ม", "วาล์ว", "เบรก",
)
_REPAIR_INTENT = (
    "ซ่อม", "repair", "ประวัติ", "downtime", "work order", "อาการที่เคย", "ครั้งล่าสุด",
)

_THAI_RE = re.compile(r"[\u0E00-\u0E7F]")
_THAI_RUN_RE = re.compile(r"[\u0E00-\u0E7F]{2,}")
_LATIN_WORD_RE = re.compile(r"[a-zA-Z]{3,}")
_MACHINE_ID_RE = re.compile(r"\b[A-Z]{2,8}[-_]?\d{2,8}\b", re.IGNORECASE)
_PART_CODE_PREFIXES = {
    "BRG",
    "CAP",
    "FAN",
    "SEAL",
    "SKF",
    "ISO",
    "VGB",
}
_SUBSTANTIVE_NUMBER_RE = re.compile(
    r"\d{2,}(?:\.\d+)?|\d+(?:°|°c|%|mm|cm|v|a|hz|kw|bar|psi|rpm|hour|hrs?|min)\b",
    re.IGNORECASE,
)
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\n+")

_EVIDENCE_TERMS = (
    "ร้อน", "ร้อนเกิน", "อุณหภูมิ", "พัดลม", "ระบายความร้อน", "ลูกปืน", "bearing",
    "สั่น", "เสียงดัง", "รั่ว", "น้ำมัน", "แรงดัน", "pressure", "ไฟ", "voltage",
    "กระแส", "current", "servo", "motor", "sensor", "alarm", "error", "fault",
    "บำรุงรักษา", "maintenance", "หล่อลื่น", "lubrication", "สตาร์ท", "starter",
    "สายพาน", "belt", "ปั๊ม", "pump", "valve", "วาล์ว", "เบรก", "brake",
    "cooling", "heat", "sink", "filter", "cleaning", "clean", "escalate",
    "escalation", "supervisor", "pre-shift", "shift", "oil", "iso", "lead",
    "stock", "สต็อก", "อะไหล่", "lockout", "loto", "breaker", "zero energy",
    "enabling", "switch", "led", "hwto", "edm", "interlock", "emergency",
    "overload", "indicator", "panel", "board",
)

_QUERY_TRIGGER_EXCLUSIONS: dict[str, tuple[str, ...]] = {
    "ร้อน": ("พักร้อน",),
    "ร้อนเกิน": ("พักร้อน",),
}

_WEAK_MANUAL_ANSWER_MARKERS = (
    "ควรตรวจสอบ",
    "แนะนำให้",
    "โดยทั่วไป",
    "อาจจะ",
    "generally",
    "typically",
    "you should",
    "it is recommended",
)

_STRICT_DOCUMENT_TYPE_TERMS: dict[str, tuple[str, ...]] = {
    "sop": ("sop", "loto", "lockout", "tagout", "lock", "tag", "breaker", "ฉุกเฉิน", "ก่อนซ่อม"),
}

_SYMPTOM_ACTION_SYMPTOM_KEYWORDS = ("ร้อน", "overheat", "temperature", "อุณหภูมิ")
_SYMPTOM_ACTION_ACTION_KEYWORDS = ("ต้องทำ", "ขั้นตอน", "วิธี")
_PROCEDURE_DOC_TYPES = frozenset({"machine_manual", "sop"})


@dataclass(frozen=True)
class GateThresholds:
    max: float
    avg: float


def is_loto_or_safety(question: str) -> bool:
    """True for LOTO / lockout-tagout / zero-energy safety questions."""
    q = (question or "").lower()
    loto_terms = (
        "loto",
        "lockout",
        "tagout",
        "lock out",
        "tag out",
        "zero energy",
        "zero-energy",
        "ล็อคเอาต์",
        "ล็อกเอาต์",
        "ติด tag",
        "ตัด breaker",
    )
    if any(term in q for term in loto_terms):
        return True
    sop_terms = _STRICT_DOCUMENT_TYPE_TERMS.get("sop", ())
    return any(term.lower() in q for term in sop_terms)


def thresholds_for_question(
    question: str,
    tuning: RagTuningContext | None = None,
) -> GateThresholds:
    """Intent-aware relevance gate thresholds on authoritative [0,1] CE scores."""
    from spark.retrieval.intent.router import IntentRouter
    from spark.retrieval.rerank.gates_config import (
        GateThresholds as RerankGateThresholds,
        thresholds_for_intent,
    )

    plan = IntentRouter().route(question)
    thresholds = thresholds_for_intent(
        plan.intent,
        tuning_max=tuning.min_max_score if tuning else None,
        tuning_avg=tuning.min_avg_score if tuning else None,
    )
    # plan.min_rerank_score is calibrated to bge post-sigmoid scores; it must
    # not override the Forge-tuned (lower) gates when Forge produces the scores.
    from spark.retrieval.rerank.gates_config import forge_gates_active

    if plan.min_rerank_score is not None and not forge_gates_active():
        thresholds = RerankGateThresholds(
            max=max(thresholds.max, float(plan.min_rerank_score)),
            avg=thresholds.avg,
        )
    return GateThresholds(max=thresholds.max, avg=thresholds.avg)


def passes_authoritative_relevance_gate(
    docs: list[RetrievedDoc],
    *,
    min_max_score: float | None = None,
    min_avg_score: float | None = None,
    question: str | None = None,
    tuning: RagTuningContext | None = None,
    intent_plan=None,
    circuit_enabled: bool = False,
    degraded: bool = False,
    degraded_policy=None,
) -> bool:
    """Absolute-threshold gate on authoritative relevance (cross-encoder or raw fusion)."""
    from spark.retrieval.rerank.gate import (
        passes_authoritative_relevance_gate as _gate,
    )

    return _gate(
        docs,
        min_max_score=min_max_score,
        min_avg_score=min_avg_score,
        question=question,
        tuning=tuning,
        intent_plan=intent_plan,
        circuit_enabled=circuit_enabled,
        degraded=degraded,
        degraded_policy=degraded_policy,
    )


def _is_symptom_action_query(question: str) -> bool:
    q = (question or "").lower()
    has_symptom = _trigger_matches(q, "ร้อน") or any(
        k in q for k in _SYMPTOM_ACTION_SYMPTOM_KEYWORDS if k != "ร้อน"
    )
    has_action = any(k in q for k in _SYMPTOM_ACTION_ACTION_KEYWORDS)
    return has_symptom and has_action


def _procedure_doc_rank(doc: RetrievedDoc) -> int:
    doc_type = doc.payload.get("document_type")
    if doc_type == "machine_manual":
        return 3
    if doc_type == "sop":
        return 2
    if doc_type == "repair_history":
        return 0
    return 1


def _docs_for_symptom_action_evidence(question: str, docs: list[RetrievedDoc]) -> list[RetrievedDoc]:
    if not _is_symptom_action_query(question):
        return docs
    filtered = [d for d in docs if d.payload.get("document_type") != "repair_history"]
    procedure = [d for d in filtered if d.payload.get("document_type") in _PROCEDURE_DOC_TYPES]
    if procedure:
        return sorted(
            procedure,
            key=lambda d: (_procedure_doc_rank(d), d.score),
            reverse=True,
        )
    return filtered or docs


def _intent_hits(question: str) -> tuple[int, int]:
    q = question.lower()
    manual_hits = sum(1 for k in _MANUAL_INTENT if k in q)
    repair_hits = sum(1 for k in _REPAIR_INTENT if k in q)
    return manual_hits, repair_hits


def _prefers_manual(question: str) -> bool:
    manual_hits, repair_hits = _intent_hits(question)
    return manual_hits > repair_hits


def _manual_preference_allowed(question: str, docs: list[RetrievedDoc]) -> bool:
    if _is_symptom_action_query(question) and any(
        d.payload.get("document_type") in _PROCEDURE_DOC_TYPES for d in docs
    ):
        return True
    if not _prefers_manual(question):
        return False
    manual_scores = [
        float(d.score) for d in docs if d.payload.get("document_type") == "machine_manual"
    ]
    if not manual_scores:
        return False
    other_scores = [
        float(d.score) for d in docs if d.payload.get("document_type") != "machine_manual"
    ]
    return max(manual_scores) >= max(other_scores, default=float("-inf"))


def _without_overridden_manuals(question: str, docs: list[RetrievedDoc]) -> list[RetrievedDoc]:
    if not _prefers_manual(question) or _manual_preference_allowed(question, docs):
        return docs
    best_other_score = max(
        (
            float(d.score)
            for d in docs
            if d.payload.get("document_type") != "machine_manual"
        ),
        default=float("-inf"),
    )
    filtered = [
        d
        for d in docs
        if d.payload.get("document_type") != "machine_manual" or float(d.score) >= best_other_score
    ]
    return filtered or docs


def _prefers_repair(question: str) -> bool:
    manual_hits, repair_hits = _intent_hits(question)
    return repair_hits > manual_hits


def _prefers_sop_safety(question: str) -> bool:
    """True when the question targets SOP / LOTO safety content (not repair-history intent)."""
    terms = _STRICT_DOCUMENT_TYPE_TERMS.get("sop", ())
    q = (question or "").lower()
    return any(term.lower() in q for term in terms)


def _should_keep_document_type_filter(question: str, rf: RAGFilter) -> bool:
    if not rf.document_type:
        return False
    terms = _STRICT_DOCUMENT_TYPE_TERMS.get(rf.document_type)
    if not terms:
        return False
    q = (question or "").lower()
    return any(term.lower() in q for term in terms)


def _trigger_matches(q: str, trigger: str) -> bool:
    trigger_l = trigger.lower()
    if trigger_l not in q:
        return False
    return not any(exclusion.lower() in q for exclusion in _QUERY_TRIGGER_EXCLUSIONS.get(trigger, ()))


def _normalize_machine_id(value: Any) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())


def _machine_ids_in_text(text: str) -> set[str]:
    return {
        _normalize_machine_id(match.group(0))
        for match in _MACHINE_ID_RE.finditer(text or "")
        if _normalize_machine_id(match.group(0)) and _is_likely_machine_identifier(match.group(0))
    }


def _is_likely_machine_identifier(raw: str) -> bool:
    match = re.match(r"([A-Z]{2,8})[-_]?\d", str(raw or "").upper())
    if not match:
        return False
    return match.group(1) not in _PART_CODE_PREFIXES


def _machine_anchors(question: str, rf: RAGFilter) -> set[str]:
    anchors = _machine_ids_in_text(question)
    if rf.machine_id:
        anchors.add(_normalize_machine_id(rf.machine_id))
    return {a for a in anchors if a}


_MIN_MACHINE_ALIAS_CHARS = 3


def _registry_ids_in_text(text: str, known_factory_machines: set[str]) -> set[str]:
    """Match machine_ids that `_MACHINE_ID_RE` can't extract because it
    requires a digit (e.g. 'MC-GOLDEN-KSS', 'MC-GOLDEN-SERVO'). Falls back to
    a whole-word match on the full id or its distinguishing last segment
    ('KSS', 'SERVO') against the question text."""
    q = text or ""
    matched: set[str] = set()
    for machine_id in known_factory_machines:
        raw = str(machine_id or "").strip()
        if not raw:
            continue
        if re.search(rf"\b{re.escape(raw)}\b", q, re.IGNORECASE):
            matched.add(_normalize_machine_id(raw))
            continue
        alias = re.split(r"[-_]", raw)[-1]
        if len(alias) >= _MIN_MACHINE_ALIAS_CHARS and re.search(
            rf"\b{re.escape(alias)}\b", q, re.IGNORECASE
        ):
            matched.add(_normalize_machine_id(raw))
    return matched


def _question_conflicts_filter_machine(
    question: str,
    rf: RAGFilter,
    *,
    known_factory_machines: set[str] | None = None,
) -> bool:
    """True when the caller scoped to one machine but the question names another."""
    if not rf.machine_id:
        return False
    filter_id = _normalize_machine_id(rf.machine_id)
    question_ids = _machine_ids_in_text(question)
    if not question_ids:
        return False
    if known_factory_machines:
        registry = {_normalize_machine_id(mid) for mid in known_factory_machines}
        question_ids = {qid for qid in question_ids if qid in registry}
        if not question_ids:
            return False
    return any(qid != filter_id for qid in question_ids)


def _filter_machine_unknown(
    rf: RAGFilter,
    known_factory_machines: set[str] | None,
) -> bool:
    """True when the caller scoped to a machine the factory registry doesn't have.

    Machine-agnostic documents match any machine_id filter (IsEmpty branch in
    the qdrant filter), so a query scoped to a nonexistent machine would still
    retrieve factory-level docs and answer — leaking an answer for a machine
    that isn't ours. Fail closed instead.
    """
    if not rf.machine_id or not known_factory_machines:
        return False
    registry = {_normalize_machine_id(mid) for mid in known_factory_machines}
    return _normalize_machine_id(rf.machine_id) not in registry


_SAFETY_BYPASS_QUERY_MARKERS = (
    "skip loto",
    "skip lockout",
    "skip tagout",
    "bypass loto",
    "bypass lockout",
    "bypass tagout",
    "bypass interlock",
    "disable safety",
    "override emergency",
    "run without guard",
    "without loto",
    "without lockout",
    "ข้าม loto",
    "ข้าม lockout",
    "ข้าม tagout",
    "ไม่ต้อง loto",
    "ไม่ต้อง lockout",
    "ไม่ต้อง tagout",
)

_NUMERIC_LIMIT_QUERY_MARKERS = (
    "สูงสุด",
    "ต่ำสุด",
    "อุณหภูมิสูงสุด",
    "อุณหภูมิต่ำสุด",
    "maximum",
    "max allowed",
    "max temperature",
    "minimum",
    "min ",
    "upper limit",
    "lower limit",
    "ไม่เกิน",
    "ไม่ต่ำกว่า",
)

# Comparative anchored to a number ("ต่ำกว่า 45 cSt ยังใช้ได้ไหม", "over 6 bar
# ok?") — a threshold-confirmation question. Echoing the asker's own number as
# the verdict is the confirmation-bias fabrication the numeric gate must block,
# so these must NOT get the question-numeric whitelist. The \s*\d anchor keeps
# plain "ร้อนเกินไป" (no number nearby) out.
_NUMERIC_COMPARATIVE_NEAR_NUMBER_RE = re.compile(
    r"(?:ต่ำกว่า|สูงกว่า|มากกว่า|น้อยกว่า|เกิน|below|above|over|under|exceeds?|"
    r"less\s+than|more\s+than)\s*\d",
    re.IGNORECASE,
)

_NUMERIC_LIMIT_EVIDENCE_MARKERS = (
    "สูงสุด",
    "ต่ำสุด",
    "maximum",
    "max ",
    "minimum",
    "min ",
    "upper limit",
    "lower limit",
    "ไม่เกิน",
    "not to exceed",
    "must not exceed",
)


def is_safety_bypass_request(question: str) -> bool:
    q = (question or "").casefold()
    return any(marker in q for marker in _SAFETY_BYPASS_QUERY_MARKERS)


def _question_requires_explicit_limit_evidence(question: str) -> bool:
    q = (question or "").casefold()
    if any(marker in q for marker in _NUMERIC_LIMIT_QUERY_MARKERS):
        return True
    return bool(_NUMERIC_COMPARATIVE_NEAR_NUMBER_RE.search(q))


def _docs_have_explicit_numeric_limit(docs: list[RetrievedDoc]) -> bool:
    for doc in docs:
        text = re.sub(r"\s+", " ", (doc.page_content or "").casefold())
        if not text:
            continue
        for marker in _NUMERIC_LIMIT_EVIDENCE_MARKERS:
            start = 0
            while True:
                idx = text.find(marker, start)
                if idx == -1:
                    break
                window = text[max(0, idx - 40): idx + 100]
                if _SUBSTANTIVE_NUMBER_RE.search(window):
                    return True
                start = idx + len(marker)
    return False


def should_refuse_rag_answer(
    question: str,
    rf: RAGFilter,
    docs: list[RetrievedDoc],
    *,
    known_factory_machines: set[str] | None = None,
) -> str | None:
    """Return a refusal reason when the query must fail closed before generation."""
    if is_safety_bypass_request(question):
        return "safety_bypass_request"
    if _question_conflicts_filter_machine(
        question, rf, known_factory_machines=known_factory_machines
    ):
        return "filter_machine_mismatch"
    if _filter_machine_unknown(rf, known_factory_machines):
        return "unknown_machine"
    if (
        docs
        and _question_requires_explicit_limit_evidence(question)
        and not _docs_have_explicit_numeric_limit(docs)
    ):
        return "numeric_limit_ungrounded"
    return None


def _payload_machine_id(payload: dict[str, Any]) -> str | None:
    raw = payload.get("machine_id")
    normalized = _normalize_machine_id(raw)
    return normalized or None


def _doc_conflicts_machine_anchors(doc: RetrievedDoc, anchors: set[str]) -> bool:
    if not anchors:
        return False

    payload_machine = _payload_machine_id(doc.payload)
    if payload_machine:
        return payload_machine not in anchors

    source_text = " ".join(
        str(doc.payload.get(k) or "")
        for k in ("source_file", "title", "machine_label")
    )
    text_machines = _machine_ids_in_text(f"{source_text}\n{doc.page_content}")
    return bool(text_machines and text_machines.isdisjoint(anchors))


def _filter_machine_conflicts(
    question: str,
    rf: RAGFilter,
    docs: list[RetrievedDoc],
    *,
    known_factory_machines: set[str] | None = None,
) -> list[RetrievedDoc]:
    anchors = _machine_anchors(question, rf)
    if known_factory_machines:
        registry_norm = {_normalize_machine_id(machine_id) for machine_id in known_factory_machines}
        text_ids = _machine_ids_in_text(question)
        anchors.update(text_ids & registry_norm)
        anchors.update(_registry_ids_in_text(question, known_factory_machines))
    if not anchors:
        return docs
    filtered = [d for d in docs if not _doc_conflicts_machine_anchors(d, anchors)]
    dropped = len(docs) - len(filtered)
    if dropped:
        log.info(
            "machine_conflict_dropped",
            dropped=dropped,
            anchors=sorted(anchors),
            factory_id=rf.factory_id,
        )
    return filtered


def _question_evidence_terms(question: str) -> set[str]:
    from spark.retrieval.intent.glossary import expand_lexical_variants
    from spark.retrieval.lexical.tokenize_industrial import extract_industrial_tokens

    expanded = expand_lexical_variants(question)
    q = (expanded or "").lower()
    q_without_machine_ids = _MACHINE_ID_RE.sub(" ", q)
    terms: set[str] = set()
    terms.update(w.lower() for w in _LATIN_WORD_RE.findall(q_without_machine_ids))
    terms.update(_extract_substantive_numbers(q_without_machine_ids))
    terms.update(t.lower() for t in extract_industrial_tokens(question, limit=24))
    for term in _EVIDENCE_TERMS:
        if _trigger_matches(q, term):
            terms.add(term.lower())
    return {t for t in terms if len(t) >= 2}


def _scope_identifier_fragments(question: str) -> set[str]:
    """Machine identifiers in the question, plus their fragments ("mc-001" →
    {"mc-001", "mc", "001"}).

    These are SCOPING signals — retrieval filters and intent boosts already
    handle them. Counting them as topical evidence let any same-machine document
    cross the evidence floor with zero on-topic terms (a warranty/label sheet
    "matched" an overheating question at 2/11 = 0.18 purely via its machine id).
    """
    frags: set[str] = set()
    for mid in _raw_machine_ids_in_text(question or ""):
        lowered = mid.lower()
        frags.add(lowered)
        for part in re.split(r"[-_/]", lowered):
            if part:
                frags.add(part)
    return frags


# Glossary-expanded terms are broad by construction ("ร้อน" → hot/heat/…, and
# short expansions substring-match inside unrelated words). They count at half
# weight, and a document matching ONLY expanded terms needs at least this many
# distinct hits before they count as evidence at all.
_EXPANDED_TERM_WEIGHT = 0.5
_MIN_EXPANDED_ONLY_HITS = 2


def _split_topical_terms(question: str) -> tuple[set[str], set[str]]:
    """Return (literal_terms, expanded_terms), both excluding scope identifiers.

    Literal terms appear verbatim in the user's question; expanded terms were
    added by the glossary (cross-lingual bridging) and are weaker evidence.
    """
    topical = _question_evidence_terms(question) - _scope_identifier_fragments(question)
    q_lower = (question or "").lower()
    literal = {t for t in topical if t in q_lower}
    return literal, topical - literal


def _weighted_topical_term_score(question: str, haystack: str) -> float:
    """Term-match evidence score over topical (non-scope) terms.

    Literal query terms count fully; glossary-expanded terms count at half
    weight and can never carry the score alone with a single broad hit.
    """
    literal, expanded = _split_topical_terms(question)
    if not literal and not expanded:
        return 0.0
    literal_hits = sum(1 for t in literal if t in haystack)
    expanded_hits = sum(1 for t in expanded if _latin_term_in_haystack(t, haystack))
    if literal_hits == 0 and expanded_hits < _MIN_EXPANDED_ONLY_HITS:
        return 0.0
    weighted_hits = literal_hits + _EXPANDED_TERM_WEIGHT * expanded_hits
    weighted_total = len(literal) + _EXPANDED_TERM_WEIGHT * len(expanded)
    return min(1.0, weighted_hits / weighted_total) if weighted_total else 0.0


_GENERIC_LATIN_QUERY_TERMS = frozenset(
    {
        "factory", "note", "target", "air", "pressure", "the", "and", "for", "with",
        "from", "show", "list", "what", "when", "where", "how", "tell", "about",
    }
)

_FACTORY_DOMAIN_LATIN = frozenset(
    {
        "factory", "machine", "motor", "servo", "bearing", "repair", "maintenance",
        "sop", "loto", "downtime", "pressure", "temperature", "cooling", "manual",
        "inspection", "certificate", "work", "order", "part", "stock", "oil", "pump",
        "valve", "alarm", "error", "fault", "iso", "pm", "shift", "startup", "bar",
        "rpm", "voltage", "current", "sensor", "belt", "fan", "heat", "overheat",
        "lubrication", "spare", "catalog", "component", "guard", "lockout", "tagout",
        "air", "target", "note", "packaging", "label", "quality", "incident",
        "checklist", "status",
        # Equipment spec-sheet vocabulary — a Thai question about an English-only
        # manual (e.g. "น้ำหนักของ KR C5 micro controller เท่าไหร่") has zero
        # same-script docs to fall back on, so it lands entirely on this list.
        # It was missing basic spec terms, silently rejecting genuinely-answerable
        # weight/rating/dimension lookups as "insufficient evidence" even when
        # the exact figure was in the top-scored retrieved chunk.
        "controller", "weight", "rating", "dimension", "dimensions", "protection",
        "capacity", "specification", "model", "axis", "axes", "robot", "payload",
        "reach", "encoder", "brake", "power", "supply", "torque", "speed", "load",
        "class", "grade", "connector", "cable", "wiring", "terminal", "diagram",
        # Safety / status vocabulary in English-only manuals (Thai questions).
        "led", "board", "system", "panel", "indicator", "csp", "enabling", "switch",
        "hwto", "edm", "eto", "interlock", "emergency", "excitation", "circuit",
        "overload", "ixt", "ksp", "output", "input", "micro", "microcontroller",
        "length", "maximum", "max", "connecting", "screw", "screws", "torx",
        "modbus", "register", "mapping", "symbolic", "link", "vacuum", "disk",
        "disc",
    }
)

_REQUIRED_ATTRIBUTE_TERMS = frozenset(
    {
        "bearing",
        "capacity",
        "coolant",
        "gearbox",
        "lubricant",
        "lubrication",
        "oil",
        "reserve",
        "temperature",
        "viscosity",
    }
)

_OFF_TOPIC_QUERY_MARKERS = frozenset(
    {
        "ramen", "recipe", "cooking", "cook ramen", "สูตรทำ", "ทำ ramen", "ทำราเมน",
    }
)


def _is_off_topic_factory_question(question: str) -> bool:
    q = (question or "").casefold()
    return any(marker in q for marker in _OFF_TOPIC_QUERY_MARKERS)


def _has_factory_domain_intent(question: str) -> bool:
    q = (question or "").casefold()
    if _machine_ids_in_text(question):
        return True
    if any(_trigger_matches(q, term) for term in _EVIDENCE_TERMS):
        return True
    if any(k in q for k in _MANUAL_INTENT):
        return True
    if any(k in q for k in _REPAIR_INTENT):
        return True
    return bool(_specific_latin_terms(question) & _FACTORY_DOMAIN_LATIN)


_MACHINE_ID_LABEL_RE = re.compile(r"\bmachine_id\b", re.IGNORECASE)


def _latin_term_in_haystack(term: str, haystack: str) -> bool:
    if term in haystack:
        return True
    if term == "micro" and ("microcontroller" in haystack or "micro controller" in haystack):
        return True
    if term == "rating" and "protection rating" in haystack:
        return True
    if term == "hwto" and re.search(r"hwto\d?", haystack):
        return True
    if term == "edm" and "edm" in haystack:
        return True
    if term == "led" and re.search(r"\bled\d?\b", haystack):
        return True
    if term in {"system", "board"} and "system board" in haystack:
        return True
    if term == "enabling" and "enabling" in haystack:
        return True
    if term == "switch" and "switch" in haystack:
        return True
    return False


def _specific_latin_terms(question: str) -> set[str]:
    from spark.retrieval.intent.glossary import expand_lexical_variants

    q = (expand_lexical_variants(question) or "").lower()
    q = _MACHINE_ID_LABEL_RE.sub(" ", q)
    q_without_machine_ids = _MACHINE_ID_RE.sub(" ", q)
    return {w.lower() for w in _LATIN_WORD_RE.findall(q_without_machine_ids)}


def _literal_latin_terms(question: str) -> set[str]:
    """Latin words the user literally typed — no glossary expansion.

    The hard required-attribute gate must key off these, not the glossary-
    expanded synonyms: a Thai question about อุณหภูมิ/ระบายความร้อน expands to
    English attribute terms ("temperature", "cooling", ...) which then get
    hard-required against a Thai document that legitimately never spells them in
    Latin — a cross-lingual false-negative that suppresses correct answers.
    """
    q = (question or "").lower()
    q = _MACHINE_ID_LABEL_RE.sub(" ", q)
    q_without_machine_ids = _MACHINE_ID_RE.sub(" ", q)
    return {w.lower() for w in _LATIN_WORD_RE.findall(q_without_machine_ids)}


def _extract_substantive_numbers(text: str) -> set[str]:
    return {m.lower() for m in _SUBSTANTIVE_NUMBER_RE.findall(text or "")}


def _has_specific_latin_coverage(question: str, docs: list[RetrievedDoc]) -> bool:
    terms = _specific_latin_terms(question) - _GENERIC_LATIN_QUERY_TERMS
    combined_haystack = " ".join(
        " ".join(
            (
                doc.page_content or "",
                str(doc.payload.get("source_file") or ""),
                str(doc.payload.get("title") or ""),
                str(doc.payload.get("document_type") or ""),
            )
        ).lower()
        for doc in docs
    )
    required_terms = (_literal_latin_terms(question) - _GENERIC_LATIN_QUERY_TERMS) & _REQUIRED_ATTRIBUTE_TERMS
    missing_required = {
        term for term in required_terms if not _latin_term_in_haystack(term, combined_haystack)
    }
    if missing_required:
        log.info(
            "rag_evidence_required_terms_rejected",
            missing=sorted(missing_required),
        )
        return False
    # Counting Latin-term coverage in the docs is only a meaningful evidence
    # signal for a Latin-script question. For a Thai-script question the docs
    # are typically Thai, so this check would always undercount and wrongly
    # reject — defer to the downstream same-script (Thai n-gram) evidence gate.
    if _thai_ratio(question) >= 0.2:
        return True
    if len(terms) < 4:
        return True

    best_hits = 0
    for doc in docs:
        haystack = " ".join(
            (
                doc.page_content or "",
                str(doc.payload.get("source_file") or ""),
                str(doc.payload.get("title") or ""),
                str(doc.payload.get("document_type") or ""),
            )
        ).lower()
        best_hits = max(best_hits, sum(1 for term in terms if _latin_term_in_haystack(term, haystack)))
    return best_hits >= 2


def _doc_evidence_score(question: str, doc: RetrievedDoc) -> float:
    from spark.retrieval.rerank.diversify import lexical_overlap_score

    literal, expanded = _split_topical_terms(question)
    if not literal and not expanded:
        return lexical_overlap_score(question, doc.page_content)

    haystack = " ".join(
        (
            doc.page_content or "",
            str(doc.payload.get("source_file") or ""),
            str(doc.payload.get("title") or ""),
            str(doc.payload.get("machine_label") or ""),
            str(doc.payload.get("document_type") or ""),
        )
    ).lower()
    term_score = _weighted_topical_term_score(question, haystack)
    return min(1.0, max(lexical_overlap_score(question, doc.page_content), term_score))


def _thai_char_ngrams(text: str, size: int = 3) -> set[str]:
    grams: set[str] = set()
    for run in _THAI_RUN_RE.findall(text or ""):
        compact = re.sub(r"\s+", "", run)
        if len(compact) <= size:
            grams.add(compact)
            continue
        grams.update(compact[i : i + size] for i in range(len(compact) - size + 1))
    return grams


def _retrieval_haystack(payload: dict[str, Any]) -> str:
    return " ".join(
        str(payload.get(key) or "")
        for key in (
            "page_content",
            "source_file",
            "title",
            "machine_id",
            "component_id",
            "document_type",
            "source_sheet",
            "row_number",
        )
    )


def _keyword_recovery_score(question: str, payload: dict[str, Any]) -> float:
    """Rank signal for the lexical retriever list (RRF uses rank, not magnitude)."""
    from spark.retrieval.rerank.diversify import lexical_overlap_score

    haystack = _retrieval_haystack(payload).lower()
    if not haystack.strip():
        return 0.0

    # Topical terms only — machine identifiers are scoping, not evidence, and
    # glossary-expanded terms are down-weighted (see _weighted_topical_term_score).
    term_score = _weighted_topical_term_score(question, haystack)

    question_without_machine_ids = _MACHINE_ID_RE.sub(" ", question or "")
    q_numbers = _extract_substantive_numbers(question_without_machine_ids)
    number_score = (
        sum(1 for n in q_numbers if n in haystack) / len(q_numbers)
        if q_numbers
        else 0.0
    )

    q_grams = _thai_char_ngrams(question)
    d_grams = _thai_char_ngrams(haystack)
    thai_score = (
        len(q_grams & d_grams) / len(q_grams)
        if q_grams and d_grams
        else 0.0
    )

    lexical_score = lexical_overlap_score(question, haystack)

    return min(1.0, max(term_score, number_score, thai_score, lexical_score))


def _raw_machine_ids_in_text(text: str) -> set[str]:
    return {
        match.group(0)
        for match in _MACHINE_ID_RE.finditer(text or "")
        if _is_likely_machine_identifier(match.group(0))
    }


def _lexical_prefilter_terms(question: str, limit: int = 12) -> list[str]:
    question_without_machine_ids = _MACHINE_ID_RE.sub(" ", question or "")
    terms: set[str] = set()
    terms.update(_question_evidence_terms(question))
    terms.update(_raw_machine_ids_in_text(question))
    terms.update(_extract_substantive_numbers(question_without_machine_ids))
    terms.update(_LATIN_WORD_RE.findall(question or ""))
    out = sorted(
        {t.strip() for t in terms if t and len(t.strip()) >= 2},
        key=lambda t: (-len(t), t.lower()),
    )
    return out[:limit]


def _coerce_uuid_strings(values: list[str] | None) -> list[str] | None:
    if values is None:
        return None
    out: list[str] = []
    for value in values:
        try:
            out.append(str(uuid.UUID(str(value))))
        except (TypeError, ValueError):
            continue
    return out


def _retrieval_identity(doc: RetrievedDoc) -> tuple[Any, ...]:
    payload = doc.payload
    chunk_id = payload.get("chunk_id")
    if chunk_id:
        return ("chunk", chunk_id)
    return (
        payload.get("doc_id"),
        payload.get("source_file"),
        payload.get("page"),
        payload.get("source_sheet"),
        payload.get("row_number"),
        payload.get("chunk_index"),
    )


def _source_identity(doc: RetrievedDoc) -> tuple[Any, ...]:
    payload = doc.payload
    doc_id = payload.get("doc_id")
    if doc_id:
        return ("doc", doc_id)
    if payload.get("source_sheet") and payload.get("row_number") is not None:
        return (
            "row",
            payload.get("source_file"),
            payload.get("source_sheet"),
            payload.get("row_number"),
        )
    return (
        "source",
        payload.get("document_type"),
        payload.get("source_file"),
        payload.get("title"),
    )


def _retrieval_sources_from_docs(docs: list[RetrievedDoc]) -> list[str]:
    sources: set[str] = set()
    for doc in docs:
        for mode in doc.payload.get("retrieval_modes") or []:
            sources.add(str(mode))
        mode = doc.payload.get("retrieval_mode")
        if mode:
            sources.add(str(mode))
    return sorted(sources)


def _thai_ratio(text: str) -> float:
    if not text:
        return 0.0
    return len(_THAI_RE.findall(text)) / max(1, len(text))


def _shares_question_script(question: str, doc: RetrievedDoc) -> bool:
    return (_thai_ratio(question) >= 0.2) == (_thai_ratio(doc.page_content) >= 0.2)


def _has_exact_evidence_match(docs: list[RetrievedDoc]) -> bool:
    for doc in docs:
        modes = set(str(mode) for mode in doc.payload.get("retrieval_modes") or [])
        mode = doc.payload.get("retrieval_mode")
        if mode:
            modes.add(str(mode))
        if not (modes & {"exact_evidence", "exact_tag"}):
            continue
        haystack = " ".join(
            (
                doc.page_content or "",
                str(doc.payload.get("page_content") or ""),
                str(doc.payload.get("source_file") or ""),
                str(doc.payload.get("title") or ""),
                str(doc.payload.get("document_type") or ""),
            )
        ).lower()
        terms = [
            str(term or "").strip().lower()
            for term in doc.payload.get("exact_terms") or []
            if len(str(term or "").strip()) >= 3
        ]
        if any(term in haystack for term in terms):
            return True
    return False


# A cross-encoder score this far above the reranker's ~0.5 no-signal baseline is
# strong, language-agnostic evidence. bge-reranker-v2-m3 is cross-lingual, so a
# Thai spec lookup ("น้ำหนัก KR C5 micro") whose answer sits in an English-only
# table scores ~0.7 here even though term-overlap sees no shared token across the
# script boundary. Trust that score for a machine-anchored chunk when the lexical
# gate would otherwise reject a genuinely-answerable question as no_data.
_RERANK_EVIDENCE_FLOOR = 0.60


def _doc_has_anchor(doc: RetrievedDoc, anchors: set[str]) -> bool:
    """True only when the doc positively carries one of the question's machine
    anchors — not merely 'does not conflict' (a doc with no machine id)."""
    if not anchors:
        return False
    payload_machine = _payload_machine_id(doc.payload)
    return bool(payload_machine and payload_machine in anchors)


def _best_anchored_rerank_score(docs: list[RetrievedDoc], anchors: set[str]) -> float:
    return max((float(d.score) for d in docs if _doc_has_anchor(d, anchors)), default=0.0)


def _has_sufficient_evidence(
    question: str, rf: RAGFilter, docs: list[RetrievedDoc]
) -> bool:
    if not docs:
        return False
    if _has_exact_evidence_match(docs):
        return True

    anchors = _machine_anchors(question, rf)
    terms = _question_evidence_terms(question)
    if not anchors and not terms:
        return True

    if _prefers_repair(question) and any(
        d.payload.get("document_type") == "repair_history" for d in docs
    ):
        return True

    if not _has_specific_latin_coverage(question, docs):
        log.info(
            "rag_evidence_specific_terms_rejected",
            terms=sorted(_specific_latin_terms(question)),
        )
        return False

    same_script_docs = [d for d in docs if _shares_question_script(question, d)]
    if not same_script_docs:
        # No same-script chunk to score lexically. Trust the cross-lingual
        # reranker when it rates a machine-anchored chunk confidently, else fall
        # back to the domain-intent heuristic.
        if _best_anchored_rerank_score(docs, anchors) >= _RERANK_EVIDENCE_FLOOR:
            return True
        from spark.retrieval.intent.glossary import expand_lexical_variants

        return _has_factory_domain_intent(expand_lexical_variants(question))

    best = max((_doc_evidence_score(question, d) for d in same_script_docs), default=0.0)
    anchored_rerank = _best_anchored_rerank_score(docs, anchors)
    log.info(
        "rag_evidence",
        best=round(best, 4),
        terms=len(terms),
        machine_anchors=sorted(anchors),
        same_script_docs=len(same_script_docs),
        anchored_rerank=round(anchored_rerank, 4),
    )
    if best >= MIN_EVIDENCE_SCORE:
        return True
    # Lexical overlap is thin (common for a Thai question answered by an
    # English-only spec table) — accept when the cross-encoder rates a
    # machine-anchored chunk well above its no-signal baseline.
    return anchored_rerank >= _RERANK_EVIDENCE_FLOOR


__all__ = [name for name in globals() if not name.startswith("__")]
