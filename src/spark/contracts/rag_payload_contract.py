"""Canonical ingest ↔ Qdrant ↔ retrieval payload field contract."""

from __future__ import annotations

import ast
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]

# All keys written to Qdrant by qdrant_router.base_payload (ingest spine).
QDRANT_PAYLOAD_FIELDS: frozenset[str] = frozenset(
    {
        "doc_id",
        "chunk_id",
        "chunk_index",
        "page",
        "source_sheet",
        "row_number",
        "extraction_source",
        "factory_id",
        "machine_id",
        "component_id",
        "document_category",
        "document_type",
        "drawing_no",
        "language",
        "revision",
        "revision_sort_key",
        "source_file",
        "title",
        "effective_date",
        "expiry_date",
        "ingested_at",
        "ingest_version",
        "ingest_generation",
        "embed_model_id",
        "embed_model",
        "embed_model_version",
        "embed_provider",
        "embed_dimension",
        "config_hash",
        "content_hash",
        "chunk_schema_version",
        "sparse_encoder_id",
        "page_content",
        "parent_chunk_id",
        "parent_index",
        "child_index_in_parent",
        "chunk_level",
        "has_tables",
        "extraction_confidence",
        "section_path",
        "retrieval_enabled",
        "boost_tokens",
        "restricted_position_ids",
        "needs_review",
        "src_path",
        "tgt_path",
    }
)

# Parser-only fields stored on PG mirror but excluded from Qdrant by default.
PARSER_PG_ONLY_FIELDS: frozenset[str] = frozenset(
    {
        "parent_content",
        "parser_version",
        "page_count",
        "block_type",
        "json_key",
        "narrative",
        "ocr_page_count",
        "ocr_char_count",
        "ocr_confidence",
        "page_ocr_confidence",
        "ocr_rejected",
        "_policy_quarantine",
        "_ocr_skipped",
    }
)

# Runtime enrichment fields not present in static base_payload literal.
QDRANT_RUNTIME_ENRICHMENT_FIELDS: frozenset[str] = frozenset(
    {"boost_tokens", "restricted_position_ids"}
)

# Parser payload fields required before index write, keyed by chunking strategy.
REQUIRED_PARSER_FIELDS_BY_CHUNKING_STRATEGY: dict[str, frozenset[str]] = {
    "page_aware_parent_child": frozenset(
        {"parent_chunk_id", "chunk_level", "parent_content", "page_content", "page"}
    ),
    "table_row": frozenset({"source_sheet", "row_number", "page_content"}),
    "sop_procedure": frozenset({"page_content", "section_path"}),
}

# Backward-compatible alias used in blueprint docs.
REQUIRED_FIELDS_BY_CHUNKING_STRATEGY = REQUIRED_PARSER_FIELDS_BY_CHUNKING_STRATEGY


def required_parser_fields_for_strategy(strategy: str | None) -> frozenset[str]:
    if not strategy:
        return frozenset({"page_content"})
    normalized = str(strategy).strip().lower()
    return REQUIRED_PARSER_FIELDS_BY_CHUNKING_STRATEGY.get(normalized, frozenset({"page_content"}))


def safety_document_types_for_audit() -> frozenset[str]:
    from spark.ingestion.quality.slo import safety_document_types

    return safety_document_types()

# Dimensions indexed/filtered during vector retrieval (_build_qdrant_filter).
# component_id is stored in payloads but deliberately NOT a filter dimension —
# product decision 2026-07: machines exist only to bind documents.
QDRANT_FILTER_DIMENSIONS: frozenset[str] = frozenset(
    {
        "doc_id",
        "factory_id",
        "machine_id",
        "document_category",
        "document_type",
        "drawing_no",
        "language",
        "revision",
        "expiry_date",
        "retrieval_enabled",
        "embed_model_version",
        "restricted_position_ids",
    }
)

# Postgres lexical mirror filter dimensions (hybrid.py WHERE clause).
POSTGRES_MIRROR_DIMENSIONS: frozenset[str] = frozenset(
    {
        "doc_id",
        "factory_id",
        "machine_id",
        "document_category",
        "document_type",
        "language",
        "expiry_date",
        "ingest_generation",
        "retrieval_enabled",
    }
)

# Filtered in Qdrant only (stored on PG chunk mirror but not lexical WHERE).
QDRANT_ONLY_FILTER_DIMENSIONS: frozenset[str] = frozenset(
    {"drawing_no", "embed_model_version", "revision", "restricted_position_ids"}
)

# Runtime-only fields added during retrieval (not persisted at ingest).
RETRIEVAL_RUNTIME_PAYLOAD_FIELDS: frozenset[str] = frozenset(
    {
        "retrieval_mode",
        "retrieval_modes",
    }
)


def _read_source(relative: str) -> str:
    return (_REPO_ROOT / relative).read_text(encoding="utf-8")


def extract_qdrant_router_payload_keys() -> frozenset[str]:
    """Parse base_payload dict keys from qdrant_writer.py."""
    tree = ast.parse(_read_source("src/spark/ingestion/index/qdrant_writer.py"))
    for node in ast.walk(tree):
        dict_node: ast.Dict | None = None
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "base_payload":
                    if isinstance(node.value, ast.Dict):
                        dict_node = node.value
        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name) and node.target.id == "base_payload":
                if isinstance(node.value, ast.Dict):
                    dict_node = node.value
        if dict_node is not None:
            keys: list[str] = []
            for key_node in dict_node.keys:
                if isinstance(key_node, ast.Constant) and isinstance(key_node.value, str):
                    keys.append(key_node.value)
            return frozenset(keys)
    raise ValueError("base_payload assignment not found in qdrant_writer.py")


def extract_qdrant_filter_keys() -> frozenset[str]:
    """Parse FieldCondition key= literals inside build_qdrant_filter."""
    text = _read_source("src/spark/retrieval/vector/filters.py")
    tree = ast.parse(text)
    keys: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "build_qdrant_filter":
            for sub in ast.walk(node):
                if isinstance(sub, ast.Call):
                    func = sub.func
                    if isinstance(func, ast.Name) and func.id == "FieldCondition":
                        for kw in sub.keywords:
                            if kw.arg == "key" and isinstance(kw.value, ast.Constant):
                                if isinstance(kw.value.value, str):
                                    keys.add(kw.value.value)
    if not keys:
        raise ValueError("build_qdrant_filter FieldCondition keys not found")
    return frozenset(keys)


def extract_postgres_mirror_filter_keys() -> frozenset[str]:
    """Parse Document / DocumentChunk filter columns from lexical scope builder."""
    text = _read_source("src/spark/retrieval/lexical/scope.py")
    keys: set[str] = set()
    if "Document.factory_id" in text:
        keys.add("factory_id")
    if "Document.machine_id" in text:
        keys.add("machine_id")
    if "Document.component_id" in text:
        keys.add("component_id")
    if "Document.document_category" in text:
        keys.add("document_category")
    if "Document.document_type" in text:
        keys.add("document_type")
    if "Document.language" in text:
        keys.add("language")
    if "Document.expiry_date" in text:
        keys.add("expiry_date")
    if "Document.doc_id" in text:
        keys.add("doc_id")
    if "DocumentChunk.ingest_generation" in text:
        keys.add("ingest_generation")
    if "Document.retrieval_enabled" in text:
        keys.add("retrieval_enabled")
    if not keys:
        raise ValueError("Postgres mirror filter keys not found in retrieval/lexical/scope.py")
    return frozenset(keys)


def render_contract_markdown() -> str:
    """Human-readable contract for docs/internal/rag_payload_contract.md."""
    lines = [
        "# RAG payload contract",
        "",
        "Generated from `src/spark/contracts/rag_payload_contract.py`. "
        "Do not edit by hand — update the contract module and re-run contract tests.",
        "",
        "## Qdrant ingest payload (`base_payload`)",
        "",
    ]
    for field in sorted(QDRANT_PAYLOAD_FIELDS):
        lines.append(f"- `{field}`")
    lines.extend(
        [
            "",
            "## Qdrant filter dimensions (`_build_qdrant_filter`)",
            "",
        ]
    )
    for field in sorted(QDRANT_FILTER_DIMENSIONS):
        lines.append(f"- `{field}`")
    lines.extend(
        [
            "",
            "## Postgres lexical mirror dimensions (`hybrid.py`)",
            "",
        ]
    )
    for field in sorted(POSTGRES_MIRROR_DIMENSIONS):
        lines.append(f"- `{field}`")
    lines.extend(
        [
            "",
            "## Invariants",
            "",
            "- Every Qdrant filter dimension MUST exist on the ingest payload.",
            "- Postgres mirror dimensions MUST match Qdrant filter dimensions plus "
            "`ingest_generation` (active-generation guard).",
            "- Retrieval-only payload keys MUST NOT be required at ingest time.",
            "",
        ]
    )
    return "\n".join(lines) + "\n"
