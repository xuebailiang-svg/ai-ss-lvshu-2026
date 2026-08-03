from __future__ import annotations

from datetime import datetime

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


RentStatus = Literal["pending_review", "confirmed", "rejected"]


class RentImportErrorItem(BaseModel):
    row: int
    reason: str


class RentImportResponse(BaseModel):
    success: bool
    project_id: str
    total_rows: int
    imported_rows: int
    failed_rows: int
    errors: list[RentImportErrorItem] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class RentListItem(BaseModel):
    id: int
    address: str | None = None
    area_sqm: float | None = None
    monthly_rent: float | None = None
    rent_unit_price: float | None = None
    property_fee: float | None = None
    transfer_fee: float | None = None
    source: str
    status: RentStatus
    timestamp: datetime | None = None
    missing_fields: list[str] = Field(default_factory=list)
    detail_completed: bool = False
    crawler_suggestion: dict | None = None


class RentListResponse(BaseModel):
    items: list[RentListItem] = Field(default_factory=list)
    total: int = 0
    incomplete_count: int = 0
    confirmed_count: int = 0
    detail_completed_count: int = 0


class RentReviewRequest(BaseModel):
    status: RentStatus


class RentManualDetail(BaseModel):
    property_type: str | None = None
    floor: str | None = None
    location_remark: str | None = None
    source_url: str | None = None
    publish_date: str | None = None
    rent_remark: str | None = None


class RentDetailResponse(RentListItem):
    manual_detail: RentManualDetail = Field(default_factory=RentManualDetail)


class RentDetailUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    property_type: str | None = None
    floor: str | None = None
    location_remark: str | None = None
    source_url: str | None = None
    publish_date: str | None = None
    rent_remark: str | None = None
