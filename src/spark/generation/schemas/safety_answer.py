"""Structured safety answer schema for procedural / LOTO generation (Phase 11)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class CitationRef(BaseModel):
    chunk_id: str = Field(min_length=1)


class SafetyAnswerSchema(BaseModel):
    steps: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    citations: list[CitationRef] = Field(default_factory=list)
    confidence: Literal["high", "medium", "low"] = "medium"
