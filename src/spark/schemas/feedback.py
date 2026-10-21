from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class FeedbackAttachmentOut(BaseModel):
    attachment_id: uuid.UUID
    sort_order: int
    mime_type: str
    url: str

    model_config = {"from_attributes": True}


class FeedbackOut(BaseModel):
    feedback_id: uuid.UUID
    factory_id: str
    machine_id: str | None = None
    source_type: str
    doc_id: uuid.UUID | None = None
    page: int | None = None
    session_id: uuid.UUID | None = None
    message_id: uuid.UUID | None = None
    comment: str
    issue_type: str | None = None
    status: str
    context: dict[str, Any] | None = None
    resolution_note: str | None = None
    resolved_by: uuid.UUID | None = None
    resolved_at: datetime | None = None
    created_by: uuid.UUID | None = None
    created_at: datetime
    attachments: list[FeedbackAttachmentOut] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class FeedbackPatch(BaseModel):
    status: str | None = None
    resolution_note: str | None = None


class FeedbackCountOut(BaseModel):
    count: int = Field(ge=0)
