from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class CollectedCounts(BaseModel):
    poi_count: int = 0
    competitor_count: int = 0
    food_count: int = 0
    entertainment_count: int = 0


class AmapCollectResponse(BaseModel):
    success: bool
    project_id: str
    collected: CollectedCounts = Field(default_factory=CollectedCounts)
    collection_status: Literal[
        "success", "success_zero", "partial", "failed", "truncated", "needs_confirmation"
    ] = "success"
    collected_at: datetime | None = None
    message: str | None = None
    diagnostics: dict[str, Any] = Field(default_factory=dict)


class AmapRawPOI(BaseModel):
    category: str
    sub_category: str
    raw: dict[str, Any]
