from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field


class BusinessOutcomeUpsert(BaseModel):
    actual_monthly_rent: float | None = Field(default=None, ge=0)
    actual_area_sqm: float | None = Field(default=None, gt=0)
    actual_machine_count: int | None = Field(default=None, ge=0)
    opening_date: date | None = None
    actual_investment: float | None = Field(default=None, ge=0)
    occupancy_rate: float | None = Field(default=None, ge=0, le=1)
    result_status: Literal["preparing", "operating", "paused", "closed", "successful", "failed"] | None = None
    success_reasons: list[str] = Field(default_factory=list)
    failure_reasons: list[str] = Field(default_factory=list)
    notes: str | None = Field(default=None, max_length=5000)


class BusinessOutcomeReview(BaseModel):
    status: Literal["pending_review", "confirmed", "rejected"]


class BusinessOutcomeResponse(BusinessOutcomeUpsert):
    id: int
    project_id: str
    status: str
    reviewed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
