"""Resource budget enforcement tests."""

from __future__ import annotations

import pytest

from spark.ingestion.budget import BudgetExceeded, ResourceBudget, ResourceBudgetTracker
from spark.ingestion.parsers.base import ParsedRecord
from spark.ingestion.reason_codes import ReasonCode


def test_budget_exceeded_on_max_chunks() -> None:
    tracker = ResourceBudgetTracker(ResourceBudget(max_chunks=3))
    for index in range(3):
        tracker.record_chunk(
            ParsedRecord(
                route="qdrant",
                payload={"page_content": f"row-{index}"},
                text_for_embedding=f"row-{index}",
            )
        )

    with pytest.raises(BudgetExceeded) as exc_info:
        tracker.record_chunk(
            ParsedRecord(
                route="qdrant",
                payload={"page_content": "overflow"},
                text_for_embedding="overflow",
            )
        )

    assert exc_info.value.reason_code == ReasonCode.BUDGET_EXCEEDED.value
    assert "max_chunks" in exc_info.value.reason_detail


def test_budget_exceeded_on_max_pages() -> None:
    tracker = ResourceBudgetTracker(ResourceBudget(max_pages=10))
    with pytest.raises(BudgetExceeded):
        tracker.record_page_count(11)
