"""Export retrieval feature rows for offline LTR training (Phase 9)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator

import pandas as pd

from spark.retrieval.intent.router import IntentPlan
from spark.retrieval.models import RetrievedDoc

FEATURE_COLUMNS = [
    "query_id",
    "intent",
    "classifier_confidence",
    "route_source",
    "dense_weight",
    "lexical_weight",
    "sparse_leg_weight",
    "document_type_hint",
    "chunk_id",
    "fusion_score",
    "vector_score",
    "lexical_score",
    "document_type",
    "rank",
]


def iter_feature_rows(
    *,
    query_id: str,
    plan: IntentPlan,
    candidates: list[RetrievedDoc],
    sparse_leg_weight: float = 0.0,
) -> Iterator[dict[str, Any]]:
    """Materialize one row per candidate for parquet export."""
    for rank, doc in enumerate(candidates, start=1):
        yield {
            "query_id": query_id,
            "intent": plan.intent.value,
            "classifier_confidence": plan.classifier_confidence,
            "route_source": plan.route_source,
            "dense_weight": plan.dense_weight,
            "lexical_weight": plan.lexical_weight,
            "sparse_leg_weight": sparse_leg_weight,
            "document_type_hint": plan.document_type_hint,
            "chunk_id": str(doc.payload.get("chunk_id") or ""),
            "fusion_score": float(doc.fusion_score if doc.fusion_score is not None else doc.score),
            "vector_score": float(doc.vector_score),
            "lexical_score": float(doc.lexical_score),
            "document_type": str(doc.payload.get("document_type") or ""),
            "rank": rank,
        }


def export_features_parquet(
    rows: list[dict[str, Any]],
    output_path: Path | str,
) -> Path:
    """Write feature rows to parquet for offline weight training."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(rows, columns=FEATURE_COLUMNS)
    frame.to_parquet(path, index=False)
    return path


def export_jsonl_log_records(
    records: list[dict[str, Any]],
    output_path: Path | str,
) -> Path:
    """Convert structured log payloads to JSONL before parquet conversion."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True))
            handle.write("\n")
    return path
