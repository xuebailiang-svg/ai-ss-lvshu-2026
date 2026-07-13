from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    city: str = Field(min_length=1, max_length=80)
    district: str | None = None
    address: str = Field(min_length=1, max_length=300)
    longitude: float | None = None
    latitude: float | None = None
    radius_meters: int = Field(default=1000, gt=0)
    business_type: str = "电竞馆"


class ProjectOut(BaseModel):
    project_id: str
    name: str | None = None
    city: str
    district: str | None = None
    address: str
    longitude: float | None = None
    latitude: float | None = None
    radius_meters: int
    business_type: str
    created_at: datetime | None = None
    deleted_at: datetime | None = None


class ProjectStats(BaseModel):
    poi_count: int
    competitor_count: int
    food_count: int
    entertainment_count: int
    missing_fields: list[str]


class ProjectDetail(BaseModel):
    project: ProjectOut
    stats: ProjectStats


class ProjectDataImport(BaseModel):
    type: Literal["poi", "competitor", "food", "entertainment", "rent", "population", "supplement"]
    data: dict[str, Any]
