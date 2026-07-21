from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


MemoryScope = Literal["global", "project", "user"]
MemoryType = Literal["preference", "business_rule", "case_feedback", "project_note", "data_source_note"]
MemoryStatus = Literal["pending_review", "confirmed", "disabled"]


class MemoryItemBase(BaseModel):
    scope: MemoryScope = "project"
    memory_type: MemoryType = "project_note"
    title: str = Field(..., min_length=1, max_length=200)
    content: str = Field(..., min_length=1)
    tags: list[str] = Field(default_factory=list)
    source: str = Field(default="manual", max_length=80)
    confidence: float = Field(default=0.7, ge=0, le=1)
    project_id: str | None = None
    user_id: str | None = None
    raw_data: dict[str, Any] = Field(default_factory=dict)


class MemoryItemCreate(MemoryItemBase):
    status: MemoryStatus = "pending_review"


class MemoryItemUpdate(BaseModel):
    scope: MemoryScope | None = None
    memory_type: MemoryType | None = None
    title: str | None = Field(default=None, min_length=1, max_length=200)
    content: str | None = Field(default=None, min_length=1)
    tags: list[str] | None = None
    source: str | None = Field(default=None, max_length=80)
    confidence: float | None = Field(default=None, ge=0, le=1)
    status: MemoryStatus | None = None
    project_id: str | None = None
    user_id: str | None = None
    raw_data: dict[str, Any] | None = None


class MemoryReviewRequest(BaseModel):
    status: MemoryStatus


class MemoryItemResponse(MemoryItemBase):
    id: int
    status: MemoryStatus
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class MemoryListResponse(BaseModel):
    items: list[MemoryItemResponse]
    total: int


class MemoryContextResponse(BaseModel):
    project_id: str
    items: list[MemoryItemResponse]
