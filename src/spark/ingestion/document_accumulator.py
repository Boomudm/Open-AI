"""Full-document state accumulator for streaming ingest (remediation v3 Phase 2)."""

from __future__ import annotations

import json
import tempfile
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from spark.ingestion.parsers.base import ParsedRecord


@dataclass
class DocumentAccumulator:
    """Holds all parsed records across streaming batches for full-doc trust/quarantine."""

    doc_id: uuid.UUID
    records: list[ParsedRecord] = field(default_factory=list)
    trust_findings: list[dict[str, Any]] = field(default_factory=list)
    batches_processed: int = 0

    def append_batch(
        self,
        batch: list[ParsedRecord],
        findings: list[dict[str, Any]] | None = None,
    ) -> None:
        if batch:
            self.records.extend(batch)
            self.batches_processed += 1
        if findings:
            self.trust_findings.extend(findings)

    def all_records(self) -> list[ParsedRecord]:
        return list(self.records)

    def record_count(self) -> int:
        return len(self.records)

    def spill_to_tempfile(self) -> Path:
        """Spill records to a temp JSON file for large-document quarantine paths."""
        payload = {
            "doc_id": str(self.doc_id),
            "records": [
                {
                    "route": rec.route,
                    "payload": rec.payload,
                    "text_for_embedding": rec.text_for_embedding,
                }
                for rec in self.records
            ],
        }
        handle = tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            suffix=".json",
            delete=False,
            prefix=f"quarantine-{self.doc_id}-",
        )
        with handle:
            json.dump(payload, handle, ensure_ascii=False)
        return Path(handle.name)
