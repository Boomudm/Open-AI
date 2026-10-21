"""The exact-tag lookup must enforce the same tenancy/ACL boundaries as the
hybrid leg — with the default single-collection shard strategy, a bare tag
filter would return another factory's io_mapping rows and bypass quarantine
and per-user document ACLs."""

from __future__ import annotations

from qdrant_client.models import FieldCondition, Filter, MatchAny, MatchValue

from spark.retrieval.models import RAGFilter
from spark.retrieval.vector.filters import build_exact_tag_filter, build_qdrant_filter


def _flatten_field_conditions(qfilter: Filter) -> list[FieldCondition]:
    found: list[FieldCondition] = []
    stack: list[Filter] = [qfilter]
    while stack:
        current = stack.pop()
        for clause_group in (current.must, current.should, current.must_not):
            for clause in clause_group or []:
                if isinstance(clause, Filter):
                    stack.append(clause)
                elif isinstance(clause, FieldCondition):
                    found.append(clause)
    return found


def _conditions_by_key(qfilter: Filter) -> dict[str, list[FieldCondition]]:
    grouped: dict[str, list[FieldCondition]] = {}
    for cond in _flatten_field_conditions(qfilter):
        grouped.setdefault(cond.key, []).append(cond)
    return grouped


def test_exact_tag_filter_scopes_to_factory() -> None:
    rf = RAGFilter(factory_id="F-01")
    qfilter = build_exact_tag_filter("RES0.BELT_CALIB_SENSOR", rf)
    keys = _conditions_by_key(qfilter)
    assert "factory_id" in keys, "exact-tag lookup must not cross factory boundaries"
    assert keys["factory_id"][0].match == MatchValue(value="F-01")


def test_exact_tag_filter_inherits_all_base_scoping() -> None:
    """Every dimension the hybrid leg filters on must constrain the tag leg too."""
    rf = RAGFilter(factory_id="F-01", machine_id="MC-01", language="th", only_active=True)
    base_keys = set(_conditions_by_key(build_qdrant_filter(rf, ["doc-1"])))
    exact_keys = set(_conditions_by_key(build_exact_tag_filter("RES0.X_1", rf, ["doc-1"])))
    missing = base_keys - exact_keys
    assert not missing, f"exact-tag filter drops base scoping dimensions: {missing}"


def test_exact_tag_filter_respects_allowed_doc_ids_acl() -> None:
    rf = RAGFilter(factory_id="F-01")
    qfilter = build_exact_tag_filter("RES0.BELT_CALIB_SENSOR", rf, ["doc-a", "doc-b"])
    keys = _conditions_by_key(qfilter)
    assert "doc_id" in keys
    assert keys["doc_id"][0].match == MatchAny(any=["doc-a", "doc-b"])


def test_exact_tag_filter_keeps_quarantine_gate() -> None:
    rf = RAGFilter(factory_id="F-01")
    keys = _conditions_by_key(build_exact_tag_filter("RES0.BELT_CALIB_SENSOR", rf))
    assert "retrieval_enabled" in keys


def test_exact_tag_filter_matches_tag_case_insensitively() -> None:
    """src_path/tgt_path are stored lowercased by the writer; the filter must
    lowercase the query-side tag so technicians typing from memory still hit."""
    rf = RAGFilter(factory_id="F-01")
    keys = _conditions_by_key(build_exact_tag_filter("RES0.Belt_Control", rf))
    assert keys["src_path"][0].match == MatchValue(value="res0.belt_control")
    assert keys["tgt_path"][0].match == MatchValue(value="res0.belt_control")


def test_exact_tag_filter_adds_io_mapping_type_once() -> None:
    rf = RAGFilter(factory_id="F-01", document_type="io_mapping")
    keys = _conditions_by_key(build_exact_tag_filter("RES0.X_1", rf))
    assert len(keys["document_type"]) == 1


def test_exact_tag_filter_never_widens_user_document_type() -> None:
    """A user filtering to another document_type must get no io_mapping rows —
    the combined filter is intentionally unsatisfiable, never widened."""
    rf = RAGFilter(factory_id="F-01", document_type="machine_manual")
    keys = _conditions_by_key(build_exact_tag_filter("RES0.X_1", rf))
    values = {c.match.value for c in keys["document_type"]}
    assert values == {"machine_manual", "io_mapping"}
