from __future__ import annotations

from typing import Any

from spark.core.config import settings
from spark.ingestion.parsers.base import ParsedRecord


class Validator:
    """Validate a parsed record against config-defined contract.

    Returns (ok, reason_code, reason_detail).
    Reason codes follow the enum documented in plan §5.4.
    """

    def validate(
        self,
        record: ParsedRecord,
        config: dict[str, Any],
        document_context: dict[str, Any] | None = None,
    ) -> tuple[bool, str | None, str | None]:
        required: list[str] = config.get("required_metadata") or []
        payload = record.payload
        ctx = document_context or {}

        for field in required:
            value = payload.get(field)
            if value is None or (isinstance(value, str) and not value.strip()):
                value = ctx.get(field)
            if value is None or (isinstance(value, str) and not value.strip()):
                return False, "missing_required", f"required field '{field}' is empty"
            if field not in payload:
                payload[field] = value

        if record.route in ("qdrant", "both"):
            if payload.get("ocr_rejected"):
                conf = payload.get("page_ocr_confidence") or payload.get("ocr_confidence")
                detail = (
                    f"OCR confidence {conf}% below index minimum "
                    f"{settings.ocr_index_min_confidence}%"
                    if conf is not None
                    else "OCR confidence below index minimum"
                )
                return False, "ocr_low_confidence", detail

            text = record.text_for_embedding or payload.get("page_content")
            if payload.get("block_type") == "table":
                text = text or payload.get("page_content") or ""
            if not text or not text.strip():
                return False, "validation_format", "empty text for embedding"

        return True, None, None
