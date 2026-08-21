from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class CompetitorCollectResponse(BaseModel):
    success: bool
    project_id: str
    provider: str
    discovered_count: int = 0
    saved_count: int = 0
    created_count: int = 0
    updated_count: int = 0
    message: str


class CompetitorListItem(BaseModel):
    id: int
    name: str
    address: str | None = None
    distance_meters: int | None = None
    source: str
    status: str
    confidence: float
    raw_category: str | None = None
    created_at: datetime | None = None
    area_sqm: float | None = None
    machine_count: int | None = None
    cpu: str | None = None
    gpu: str | None = None
    monitor: str | None = None
    hour_price: float | None = None
    member_price: float | None = None
    business_hours: str | None = None
    opening_date: str | None = None
    occupancy_rate: float | None = None
    monthly_sales: float | None = None
    annual_sales: float | None = None
    recharge_info: str | None = None
    remark: str | None = None
    occupancy_observed_at: str | None = None
    occupancy_period: str | None = None
    survey_method: str | None = None
    sales_source: str | None = None
    manual_meta: dict = Field(default_factory=dict)


class CompetitorListResponse(BaseModel):
    items: list[CompetitorListItem] = Field(default_factory=list)
    total: int = 0


class CompetitorReviewRequest(BaseModel):
    status: Literal["confirmed", "rejected", "pending_review"]


class CompetitorDetailUpdate(BaseModel):
    area_sqm: float | None = Field(default=None, ge=0)
    machine_count: int | None = Field(default=None, ge=0)
    cpu: str | None = None
    gpu: str | None = None
    monitor: str | None = None
    hour_price: float | None = Field(default=None, ge=0)
    member_price: float | None = Field(default=None, ge=0)
    business_hours: str | None = None
    opening_date: str | None = None
    occupancy_rate: float | None = Field(default=None, ge=0, le=1)
    monthly_sales: float | None = Field(default=None, ge=0)
    annual_sales: float | None = Field(default=None, ge=0)
    recharge_info: str | None = None
    remark: str | None = None
    occupancy_observed_at: str | None = None
    occupancy_period: str | None = None
    survey_method: str | None = None
    sales_source: str | None = None
    unknown_fields: list[str] = Field(default_factory=list)

    @field_validator("occupancy_rate", mode="before")
    @classmethod
    def normalize_occupancy_rate(cls, value):
        if value is None or value == "":
            return None
        text = str(value).strip()
        number = float(text.rstrip("%"))
        if text.endswith("%") or number > 1:
            number /= 100
        return number
