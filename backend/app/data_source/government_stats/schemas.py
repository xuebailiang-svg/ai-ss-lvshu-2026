from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, HttpUrl


ReviewStatus = Literal["confirmed", "pending_review", "rejected"]


class GovernmentStatsSyncRequest(BaseModel):
    city: str
    district: str | None = None
    sources: list[str] = Field(default_factory=lambda: ["national", "shaanxi", "xian"])
    force_refresh: bool = False


class GovernmentStatisticReview(BaseModel):
    status: ReviewStatus


class GovernmentStatisticUploadRow(BaseModel):
    metric_code: str
    metric_name: str
    value_numeric: float | None = None
    value_text: str | None = None
    unit: str | None = None
    scope_level: Literal["country", "province", "city", "district"]
    scope_code: str
    scope_name: str
    stat_period: str
    source_name: str
    source_url: HttpUrl
    source_format: Literal["api", "html", "xlsx", "pdf", "manual"] = "manual"
    raw_data: dict[str, Any] = Field(default_factory=dict)


class GovernmentStatisticUpload(BaseModel):
    items: list[GovernmentStatisticUploadRow]
