from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class SupportingAnalysis(BaseModel):
    food_count: int = 0
    entertainment_count: int = 0
    night_business_count: int = 0
    night_activity_level: Literal["none", "low", "medium", "high"] = "none"


class SupportingCollectResponse(BaseModel):
    success: bool
    project_id: str
    provider: str
    food_count: int = 0
    entertainment_count: int = 0
    night_business_count: int = 0
    created_count: int = 0
    updated_count: int = 0
    supporting_analysis: SupportingAnalysis
    warnings: list[str] = Field(default_factory=list)
    message: str


SupportingStatus = Literal["pending_review", "confirmed", "rejected"]
SupportingCategory = Literal["food", "entertainment", "night_business"]


class SupportingListItem(BaseModel):
    id: str
    name: str
    category: SupportingCategory
    address: str | None = None
    distance_meters: int | None = None
    source: str
    status: SupportingStatus
    detail_completed: bool = False


class SupportingCategoryStats(BaseModel):
    total: int = 0
    confirmed: int = 0
    pending_review: int = 0
    rejected: int = 0


class SupportingListResponse(BaseModel):
    items: list[SupportingListItem] = Field(default_factory=list)
    total: int = 0
    effective_count: int = 0
    stats: dict[str, SupportingCategoryStats] = Field(default_factory=dict)


class SupportingReviewRequest(BaseModel):
    status: SupportingStatus


class SupportingManualDetail(BaseModel):
    business_hours: str | None = None
    opening_date: str | None = None
    remark: str | None = None
    food_type: str | None = None
    entertainment_type: str | None = None
    night_operation: bool | None = None
    is_24_hours: bool | None = None
    night_flow_remark: str | None = None


class SupportingDetailResponse(SupportingListItem):
    manual_detail: SupportingManualDetail = Field(default_factory=SupportingManualDetail)


class SupportingDetailUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    business_hours: str | None = None
    opening_date: str | None = None
    remark: str | None = None
    food_type: str | None = None
    entertainment_type: str | None = None
    night_operation: bool | None = None
    is_24_hours: bool | None = None
    night_flow_remark: str | None = None
