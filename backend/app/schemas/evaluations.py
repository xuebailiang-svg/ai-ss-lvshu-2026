from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class PropertyIn(BaseModel):
    area_sqm: float | None = Field(None, ge=0)
    usable_area_sqm: float | None = Field(None, ge=0)
    monthly_rent: float | None = Field(None, ge=0)
    rent_per_sqm_day: float | None = Field(None, ge=0)
    rent_per_sqm_month: float | None = Field(None, ge=0)
    floor: str | None = None
    floor_height_m: float | None = Field(None, ge=0)
    property_fee_monthly: float | None = Field(None, ge=0)
    transfer_fee: float | None = Field(None, ge=0)
    deposit: float | None = Field(None, ge=0)
    rent_free_months: float | None = Field(None, ge=0)
    lease_term_months: int | None = Field(None, ge=0)
    rent_escalation: str | None = None
    power_capacity_kw: float | None = Field(None, ge=0)
    power_expansion_allowed: bool | None = None
    network_carriers: str | None = None
    dual_line_supported: bool | None = None
    night_entrance: bool | None = None
    use_allowed: bool | None = None
    fire_confirmed: bool | None = None
    sprinkler: bool | None = None
    smoke_exhaust: bool | None = None
    safety_exit_count: int | None = Field(None, ge=0)
    parking_condition: str | None = None
    facade_width_m: float | None = Field(None, ge=0)
    street_facing: bool | None = None
    facade_visibility: str | None = None
    noise_complaint_risk: str | None = None
    required_rectifications: str | None = None
    property_contact: str | None = None
    machine_count: int | None = Field(None, ge=0)
    rent_per_machine_month: float | None = Field(None, ge=0)
    power_sufficient: bool | None = None
    surveyed_at: datetime | None = None
    source: str | None = None
    confidence: float = Field(0.5, ge=0, le=1)
    verified_at: datetime | None = None
    notes: str | None = None


class EvaluationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    city: str = Field(min_length=1, max_length=50)
    address: str = Field(min_length=1, max_length=300)
    radius: int = Field(3000, ge=100, le=50000)
    property: PropertyIn = PropertyIn()


class SiteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    formatted_address: str | None
    district: str | None
    longitude: float | None
    latitude: float | None
    coordinate_system: str
    provider: str


class EvaluationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    city: str
    address: str
    radius: int
    status: str
    error_message: str | None
    created_at: datetime
    site: SiteOut | None = None


class CompetitorEnrichmentIn(BaseModel):
    opened_at_estimate: str | None = None
    opening_basis: str | None = None
    machine_count: int | None = Field(None, ge=0)
    area_sqm: float | None = Field(None, ge=0)
    cpu: str | None = None
    gpu: str | None = None
    monitor_size_inch: float | None = Field(None, ge=0)
    monitor_refresh_rate: int | None = Field(None, ge=0)
    normal_price: float | None = Field(None, ge=0)
    premium_price: float | None = Field(None, ge=0)
    private_room_price: float | None = Field(None, ge=0)
    member_price: float | None = Field(None, ge=0)
    recharge_promotion: str | None = None
    peak_occupancy_rate: float | None = Field(None, ge=0, le=1)
    offpeak_occupancy_rate: float | None = Field(None, ge=0, le=1)
    surveyed_at: datetime | None = None
    survey_method: str | None = None
    source: str | None = None
    confidence: float = Field(0.5, ge=0, le=1)
    verified_at: datetime | None = None
    is_manually_verified: bool = False
    notes: str | None = None
    hardware: dict[str, Any] = {}
    pricing: dict[str, Any] = {}
    occupancy: dict[str, Any] = {}


class ComparisonIn(BaseModel):
    evaluation_ids: list[int] = Field(min_length=2, max_length=5)
