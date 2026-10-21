from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

Route = Literal["qdrant", "postgres", "both"]


class ParserError(RuntimeError):
    """Parser-level failure that should surface as an ingestion failure reason."""

    def __init__(self, reason_code: str, reason_detail: str) -> None:
        super().__init__(reason_detail)
        self.reason_code = reason_code
        self.reason_detail = reason_detail


@dataclass
class ParsedRecord:
    """A single record emitted by a parser plugin.

    Qdrant-route payloads are validated against ``ParsedRecordPayload`` (extra=forbid).
    Postgres-route payloads use table-specific allowlists at write time.
    """

    route: Route
    payload: dict[str, Any]
    text_for_embedding: str | None = None
    target_table: str | None = None
    source_locator: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.route != "qdrant":
            return
        from spark.contracts.parsed_record_schema import validate_parser_payload

        self.payload = validate_parser_payload(self.payload)

    @classmethod
    def qdrant(
        cls,
        *,
        payload: dict[str, Any],
        text_for_embedding: str | None = None,
        source_locator: dict[str, Any] | None = None,
    ) -> ParsedRecord:
        return cls(
            route="qdrant",
            payload=payload,
            text_for_embedding=text_for_embedding,
            source_locator=source_locator or {},
        )


class ParserPlugin(ABC):
    name: str = ""
    supported_extensions: tuple[str, ...] = ()

    @abstractmethod
    async def parse(self, file_path: Path, config: dict[str, Any]) -> AsyncIterator[ParsedRecord]:
        """Yield ParsedRecord items. Must be an async generator."""
        if False:
            yield ParsedRecord(route="qdrant", payload={"page_content": ""})
