from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .enums import DataSourceType, DataStatus, EntertainmentType, POICategory
from .validators import blank_to_none, utc_now


class StrictBaseModel(BaseModel):
    model_config = ConfigDict(use_enum_values=True, populate_by_name=True)

    @field_validator("*", mode="before")
    @classmethod
    def normalize_blank(cls, value: Any) -> Any:
        return blank_to_none(value)


class BaseDataSource(StrictBaseModel):
    source: DataSourceType = DataSourceType.manual
    timestamp: datetime = Field(default_factory=utc_now)
    confidence: float = Field(default=0.5, ge=0, le=1)
    status: DataStatus = DataStatus.pending_review
    raw_data: dict[str, Any] = Field(default_factory=dict)


class SiteProject(BaseDataSource):
    project_id: str | None = None
    project_name: str | None = None
    city: str
    district: str | None = None
    address: str
    longitude: float | None = None
    latitude: float | None = None
    radius_meters: int = 1000
    business_type: str = "电竞馆"
    created_at: datetime = Field(default_factory=utc_now)


class POIData(BaseDataSource):
    name: str
    category: POICategory = POICategory.other
    sub_category: str | None = None
    address: str | None = None
    longitude: float | None = None
    latitude: float | None = None
    distance_meters: int | None = None
    walking_distance_meters: int | None = None
    business_hours: str | None = None


class CompetitorData(BaseDataSource):
    name: str
    address: str | None = None
    distance_meters: int | None = None
    area_sqm: float | None = None
    opening_date: str | None = None
    opening_years: float | None = None
    machine_count: int | None = None
    cpu: str | None = None
    gpu: str | None = None
    monitor: str | None = None
    hour_price: float | None = None
    member_price: float | None = None
    occupancy_rate: float | None = None
    monthly_sales: float | None = None
    annual_sales: float | None = None
    recharge_amount: float | None = None


class FoodBusinessData(BaseDataSource):
    name: str
    distance_meters: int | None = None
    category: str | None = None
    opening_date: str | None = None
    opening_years: float | None = None
    business_hours: str | None = None
    night_business: bool | None = None
    rating: float | None = None


class EntertainmentData(BaseDataSource):
    name: str
    type: EntertainmentType = EntertainmentType.other
    distance_meters: int | None = None
    opening_date: str | None = None
    business_hours: str | None = None
    night_business: bool | None = None


class RentData(BaseDataSource):
    monthly_rent: float | None = None
    area_sqm: float | None = None
    rent_per_sqm: float | None = None
    location_type: str | None = None


class PopulationData(BaseDataSource):
    nearby_university_count: int | None = None
    nearby_school_count: int | None = None
    nearby_apartment_count: int | None = None
    nearby_residential_count: int | None = None
    young_population_indicator: float | None = None


class SupplementData(BaseDataSource):
    project_id: str | None = None
    target_type: str
    target_id: str | int | None = None
    field_name: str
    value: Any = None
    created_time: datetime = Field(default_factory=utc_now)
