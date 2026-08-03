import enum
from datetime import date, datetime, timezone
from typing import Any
from sqlalchemy import Boolean, Date, DateTime, Enum, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base

def now(): return datetime.now(timezone.utc)
class JobStatus(str, enum.Enum):
    pending="pending"; running="running"; completed="completed"; failed="failed"

class SiteEvaluation(Base):
    __tablename__="site_evaluations"
    id: Mapped[int]=mapped_column(primary_key=True)
    name: Mapped[str]=mapped_column(String(120)); city: Mapped[str]=mapped_column(String(50)); address: Mapped[str]=mapped_column(String(300))
    radius: Mapped[int]=mapped_column(default=3000); status: Mapped[JobStatus]=mapped_column(Enum(JobStatus), default=JobStatus.pending)
    error_message: Mapped[str|None]=mapped_column(Text); created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=now); updated_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=now, onupdate=now)
    site: Mapped["CandidateSite"]=relationship(back_populates="evaluation", cascade="all, delete-orphan", uselist=False)
    pois: Mapped[list["PoiObservation"]]=relationship(back_populates="evaluation", cascade="all, delete-orphan")
    result: Mapped["ScoringResult|None"]=relationship(back_populates="evaluation", cascade="all, delete-orphan", uselist=False)

class CandidateSite(Base):
    __tablename__="candidate_sites"
    id: Mapped[int]=mapped_column(primary_key=True); evaluation_id: Mapped[int]=mapped_column(ForeignKey("site_evaluations.id"), unique=True)
    formatted_address: Mapped[str|None]=mapped_column(String(300)); district: Mapped[str|None]=mapped_column(String(100)); longitude: Mapped[float|None]=mapped_column(Float); latitude: Mapped[float|None]=mapped_column(Float)
    coordinate_system: Mapped[str]=mapped_column(String(20), default="GCJ02"); provider: Mapped[str]=mapped_column(String(30), default="amap")
    evaluation: Mapped[SiteEvaluation]=relationship(back_populates="site"); property_survey: Mapped["PropertySurvey|None"]=relationship(cascade="all, delete-orphan", uselist=False, back_populates="site")

class PropertySurvey(Base):
    __tablename__="property_surveys"
    id: Mapped[int]=mapped_column(primary_key=True); candidate_site_id: Mapped[int]=mapped_column(ForeignKey("candidate_sites.id"), unique=True)
    area_sqm: Mapped[float|None]=mapped_column(Float); monthly_rent: Mapped[float|None]=mapped_column(Float); floor: Mapped[str|None]=mapped_column(String(30)); street_facing: Mapped[bool|None]=mapped_column(Boolean)
    night_entrance: Mapped[bool|None]=mapped_column(Boolean); use_allowed: Mapped[bool|None]=mapped_column(Boolean); power_sufficient: Mapped[bool|None]=mapped_column(Boolean); fire_confirmed: Mapped[bool|None]=mapped_column(Boolean); notes: Mapped[str|None]=mapped_column(Text)
    usable_area_sqm: Mapped[float|None]=mapped_column(Float); floor_height_m: Mapped[float|None]=mapped_column(Float); rent_per_sqm_day: Mapped[float|None]=mapped_column(Float); rent_per_sqm_month: Mapped[float|None]=mapped_column(Float); property_fee_monthly: Mapped[float|None]=mapped_column(Float); transfer_fee: Mapped[float|None]=mapped_column(Float); deposit: Mapped[float|None]=mapped_column(Float); rent_free_months: Mapped[float|None]=mapped_column(Float); lease_term_months: Mapped[int|None]=mapped_column(Integer); rent_escalation: Mapped[str|None]=mapped_column(String(200))
    power_capacity_kw: Mapped[float|None]=mapped_column(Float); power_expansion_allowed: Mapped[bool|None]=mapped_column(Boolean); network_carriers: Mapped[str|None]=mapped_column(String(200)); dual_line_supported: Mapped[bool|None]=mapped_column(Boolean)
    sprinkler: Mapped[bool|None]=mapped_column(Boolean); smoke_exhaust: Mapped[bool|None]=mapped_column(Boolean); safety_exit_count: Mapped[int|None]=mapped_column(Integer); parking_condition: Mapped[str|None]=mapped_column(String(200)); facade_width_m: Mapped[float|None]=mapped_column(Float); facade_visibility: Mapped[str|None]=mapped_column(String(100)); noise_complaint_risk: Mapped[str|None]=mapped_column(String(100)); required_rectifications: Mapped[str|None]=mapped_column(Text); property_contact: Mapped[str|None]=mapped_column(String(120))
    machine_count: Mapped[int|None]=mapped_column(Integer); rent_per_machine_month: Mapped[float|None]=mapped_column(Float); surveyed_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True)); source: Mapped[str|None]=mapped_column(String(100)); confidence: Mapped[float]=mapped_column(Float, default=.5); verified_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True)); updated_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=now, onupdate=now)
    site: Mapped[CandidateSite]=relationship(back_populates="property_survey")

class PoiObservation(Base):
    __tablename__="poi_observations"
    id: Mapped[int]=mapped_column(primary_key=True); evaluation_id: Mapped[int]=mapped_column(ForeignKey("site_evaluations.id"), index=True)
    source: Mapped[str]=mapped_column(String(30), default="amap"); provider_record_id: Mapped[str]=mapped_column(String(100)); name: Mapped[str]=mapped_column(String(200)); category: Mapped[str]=mapped_column(String(50)); type_code: Mapped[str|None]=mapped_column(String(30)); address: Mapped[str|None]=mapped_column(String(300))
    longitude: Mapped[float|None]=mapped_column(Float); latitude: Mapped[float|None]=mapped_column(Float); coordinate_system: Mapped[str]=mapped_column(String(20), default="GCJ02"); distance_m: Mapped[int|None]=mapped_column(Integer); phone: Mapped[str|None]=mapped_column(String(100)); business_hours: Mapped[str|None]=mapped_column(String(200)); business_area: Mapped[str|None]=mapped_column(String(100))
    observed_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=now); fetched_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=now); confidence: Mapped[float]=mapped_column(Float, default=.75); is_estimated: Mapped[bool]=mapped_column(Boolean, default=False); is_manually_verified: Mapped[bool]=mapped_column(Boolean, default=False); needs_verification: Mapped[bool]=mapped_column(Boolean, default=False); raw_data: Mapped[dict[str,Any]]=mapped_column(JSON, default=dict)
    evaluation: Mapped[SiteEvaluation]=relationship(back_populates="pois"); enrichment: Mapped["CompetitorEnrichment|None"]=relationship(cascade="all, delete-orphan", uselist=False, back_populates="poi"); generic_enrichment: Mapped["PoiEnrichment|None"]=relationship(cascade="all, delete-orphan", uselist=False, back_populates="poi"); survey_records: Mapped[list["CompetitorSurveyRecord"]]=relationship(cascade="all, delete-orphan", back_populates="poi", order_by="CompetitorSurveyRecord.created_at.desc()")

class PoiEnrichment(Base):
    __tablename__="poi_enrichments"
    id: Mapped[int]=mapped_column(primary_key=True); poi_observation_id: Mapped[int]=mapped_column(ForeignKey("poi_observations.id"), unique=True, index=True)
    category: Mapped[str]=mapped_column(String(50)); payload: Mapped[dict[str,Any]]=mapped_column(JSON, default=dict); data_source: Mapped[str]=mapped_column(String(50), default="manual"); verification_status: Mapped[str]=mapped_column(String(50), default="未核实")
    is_verified: Mapped[bool]=mapped_column(Boolean, default=False); verified_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True)); created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=now); updated_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=now, onupdate=now)
    poi: Mapped[PoiObservation]=relationship(back_populates="generic_enrichment")

class CompetitorEnrichment(Base):
    __tablename__="competitor_enrichments"
    id: Mapped[int]=mapped_column(primary_key=True); poi_observation_id: Mapped[int]=mapped_column(ForeignKey("poi_observations.id"), unique=True)
    opened_at_estimate: Mapped[str|None]=mapped_column(String(50)); machine_count: Mapped[int|None]=mapped_column(Integer); area_sqm: Mapped[float|None]=mapped_column(Float); hardware: Mapped[dict[str,Any]]=mapped_column(JSON, default=dict); pricing: Mapped[dict[str,Any]]=mapped_column(JSON, default=dict); occupancy: Mapped[dict[str,Any]]=mapped_column(JSON, default=dict); source: Mapped[str|None]=mapped_column(String(100)); surveyed_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True)); confidence: Mapped[float]=mapped_column(Float, default=.5); notes: Mapped[str|None]=mapped_column(Text)
    cpu: Mapped[str|None]=mapped_column(String(100)); gpu: Mapped[str|None]=mapped_column(String(100)); monitor_size_inch: Mapped[float|None]=mapped_column(Float); monitor_refresh_rate: Mapped[int|None]=mapped_column(Integer)
    normal_price: Mapped[float|None]=mapped_column(Float); premium_price: Mapped[float|None]=mapped_column(Float); private_room_price: Mapped[float|None]=mapped_column(Float); member_price: Mapped[float|None]=mapped_column(Float); recharge_promotion: Mapped[str|None]=mapped_column(String(300))
    opening_basis: Mapped[str|None]=mapped_column(String(300)); peak_occupancy_rate: Mapped[float|None]=mapped_column(Float); offpeak_occupancy_rate: Mapped[float|None]=mapped_column(Float); survey_method: Mapped[str|None]=mapped_column(String(100)); verified_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True)); is_manually_verified: Mapped[bool]=mapped_column(Boolean, default=False); updated_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=now, onupdate=now)
    poi: Mapped[PoiObservation]=relationship(back_populates="enrichment")

class CompetitorSurveyRecord(Base):
    __tablename__="competitor_survey_records"
    id: Mapped[int]=mapped_column(primary_key=True); poi_observation_id: Mapped[int]=mapped_column(ForeignKey("poi_observations.id"), index=True)
    payload: Mapped[dict[str,Any]]=mapped_column(JSON, default=dict); source: Mapped[str|None]=mapped_column(String(100)); confidence: Mapped[float]=mapped_column(Float, default=.5); verified_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True)); created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=now)
    poi: Mapped[PoiObservation]=relationship(back_populates="survey_records")

class RegulationRule(Base):
    __tablename__="regulation_rules"
    id: Mapped[int]=mapped_column(primary_key=True); city: Mapped[str]=mapped_column(String(50), default="*"); sensitive_type: Mapped[str]=mapped_column(String(50)); limit_distance_m: Mapped[int|None]=mapped_column(Integer); calculation_method: Mapped[str]=mapped_column(String(30), default="provider_distance"); risk_level: Mapped[str]=mapped_column(String(20)); policy_basis: Mapped[str]=mapped_column(Text); effective_date: Mapped[date|None]=mapped_column(Date); manual_review: Mapped[bool]=mapped_column(Boolean, default=True); enabled: Mapped[bool]=mapped_column(Boolean, default=True)

class ScoringModel(Base):
    __tablename__="scoring_models"
    id: Mapped[int]=mapped_column(primary_key=True); version: Mapped[str]=mapped_column(String(30), unique=True); config: Mapped[dict[str,Any]]=mapped_column(JSON); active: Mapped[bool]=mapped_column(Boolean, default=True); created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=now)
class ScoringResult(Base):
    __tablename__="scoring_results"
    id: Mapped[int]=mapped_column(primary_key=True); evaluation_id: Mapped[int]=mapped_column(ForeignKey("site_evaluations.id"), unique=True); total_score: Mapped[float]=mapped_column(Float); recommendation: Mapped[str]=mapped_column(String(30)); dimensions: Mapped[dict[str,Any]]=mapped_column(JSON); positive_evidence: Mapped[list[Any]]=mapped_column(JSON); negative_evidence: Mapped[list[Any]]=mapped_column(JSON); hard_risks: Mapped[list[Any]]=mapped_column(JSON); review_items: Mapped[list[Any]]=mapped_column(JSON); completeness: Mapped[float]=mapped_column(Float); confidence: Mapped[float]=mapped_column(Float); model_version: Mapped[str]=mapped_column(String(30)); created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=now)
    evaluation: Mapped[SiteEvaluation]=relationship(back_populates="result")
class EvaluationReport(Base):
    __tablename__="evaluation_reports"
    id: Mapped[int]=mapped_column(primary_key=True); evaluation_id: Mapped[int]=mapped_column(ForeignKey("site_evaluations.id"), unique=True); renderer: Mapped[str]=mapped_column(String(30)); content: Mapped[dict[str,Any]]=mapped_column(JSON); generated_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=now)
class DataSource(Base):
    __tablename__="data_sources"
    id: Mapped[int]=mapped_column(primary_key=True); name: Mapped[str]=mapped_column(String(100), unique=True); provider: Mapped[str]=mapped_column(String(50)); description: Mapped[str|None]=mapped_column(Text); enabled: Mapped[bool]=mapped_column(Boolean, default=True)

class SiteProjectRecord(Base):
    __tablename__="site_projects"
    id: Mapped[int]=mapped_column(primary_key=True)
    project_id: Mapped[str]=mapped_column(String(80), unique=True, index=True)
    project_name: Mapped[str|None]=mapped_column(String(160))
    city: Mapped[str]=mapped_column(String(80))
    district: Mapped[str|None]=mapped_column(String(80))
    address: Mapped[str]=mapped_column(String(300))
    longitude: Mapped[float|None]=mapped_column(Float)
    latitude: Mapped[float|None]=mapped_column(Float)
    radius_meters: Mapped[int]=mapped_column(Integer, default=1000)
    business_type: Mapped[str]=mapped_column(String(80), default="电竞馆")
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=now)
    source: Mapped[str]=mapped_column(String(50), default="manual")
    timestamp: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=now)
    confidence: Mapped[float]=mapped_column(Float, default=.5)
    status: Mapped[str]=mapped_column(String(50), default="pending_review")
    raw_data: Mapped[dict[str,Any]]=mapped_column(JSON, default=dict)
    deleted_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True))

class UnifiedPOIRecord(Base):
    __tablename__="pois"
    id: Mapped[int]=mapped_column(primary_key=True)
    project_id: Mapped[str|None]=mapped_column(String(80), index=True)
    name: Mapped[str]=mapped_column(String(200))
    category: Mapped[str]=mapped_column(String(50), index=True)
    sub_category: Mapped[str|None]=mapped_column(String(100))
    address: Mapped[str|None]=mapped_column(String(300))
    longitude: Mapped[float|None]=mapped_column(Float)
    latitude: Mapped[float|None]=mapped_column(Float)
    distance_meters: Mapped[int|None]=mapped_column(Integer)
    walking_distance_meters: Mapped[int|None]=mapped_column(Integer)
    business_hours: Mapped[str|None]=mapped_column(String(200))
    source: Mapped[str]=mapped_column(String(50), default="manual")
    timestamp: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=now)
    confidence: Mapped[float]=mapped_column(Float, default=.5)
    status: Mapped[str]=mapped_column(String(50), default="pending_review")
    raw_data: Mapped[dict[str,Any]]=mapped_column(JSON, default=dict)

class UnifiedCompetitorRecord(Base):
    __tablename__="competitors"
    id: Mapped[int]=mapped_column(primary_key=True)
    project_id: Mapped[str|None]=mapped_column(String(80), index=True)
    name: Mapped[str]=mapped_column(String(200))
    address: Mapped[str|None]=mapped_column(String(300))
    distance_meters: Mapped[int|None]=mapped_column(Integer)
    area_sqm: Mapped[float|None]=mapped_column(Float)
    opening_date: Mapped[str|None]=mapped_column(String(50))
    opening_years: Mapped[float|None]=mapped_column(Float)
    machine_count: Mapped[int|None]=mapped_column(Integer)
    cpu: Mapped[str|None]=mapped_column(String(120))
    gpu: Mapped[str|None]=mapped_column(String(120))
    monitor: Mapped[str|None]=mapped_column(String(120))
    hour_price: Mapped[float|None]=mapped_column(Float)
    member_price: Mapped[float|None]=mapped_column(Float)
    occupancy_rate: Mapped[float|None]=mapped_column(Float)
    monthly_sales: Mapped[float|None]=mapped_column(Float)
    annual_sales: Mapped[float|None]=mapped_column(Float)
    recharge_amount: Mapped[float|None]=mapped_column(Float)
    source: Mapped[str]=mapped_column(String(50), default="manual")
    timestamp: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=now)
    confidence: Mapped[float]=mapped_column(Float, default=.5)
    status: Mapped[str]=mapped_column(String(50), default="pending_review")
    raw_data: Mapped[dict[str,Any]]=mapped_column(JSON, default=dict)

class FoodBusinessRecord(Base):
    __tablename__="food_businesses"
    id: Mapped[int]=mapped_column(primary_key=True)
    project_id: Mapped[str|None]=mapped_column(String(80), index=True)
    name: Mapped[str]=mapped_column(String(200))
    distance_meters: Mapped[int|None]=mapped_column(Integer)
    category: Mapped[str|None]=mapped_column(String(80))
    opening_date: Mapped[str|None]=mapped_column(String(50))
    opening_years: Mapped[float|None]=mapped_column(Float)
    business_hours: Mapped[str|None]=mapped_column(String(200))
    night_business: Mapped[bool|None]=mapped_column(Boolean)
    rating: Mapped[float|None]=mapped_column(Float)
    source: Mapped[str]=mapped_column(String(50), default="manual")
    timestamp: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=now)
    confidence: Mapped[float]=mapped_column(Float, default=.5)
    status: Mapped[str]=mapped_column(String(50), default="pending_review")
    raw_data: Mapped[dict[str,Any]]=mapped_column(JSON, default=dict)

class EntertainmentRecord(Base):
    __tablename__="entertainments"
    id: Mapped[int]=mapped_column(primary_key=True)
    project_id: Mapped[str|None]=mapped_column(String(80), index=True)
    name: Mapped[str]=mapped_column(String(200))
    type: Mapped[str]=mapped_column(String(50), default="other")
    distance_meters: Mapped[int|None]=mapped_column(Integer)
    opening_date: Mapped[str|None]=mapped_column(String(50))
    business_hours: Mapped[str|None]=mapped_column(String(200))
    night_business: Mapped[bool|None]=mapped_column(Boolean)
    source: Mapped[str]=mapped_column(String(50), default="manual")
    timestamp: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=now)
    confidence: Mapped[float]=mapped_column(Float, default=.5)
    status: Mapped[str]=mapped_column(String(50), default="pending_review")
    raw_data: Mapped[dict[str,Any]]=mapped_column(JSON, default=dict)

class RentDataRecord(Base):
    __tablename__="rent_data"
    id: Mapped[int]=mapped_column(primary_key=True)
    project_id: Mapped[str|None]=mapped_column(String(80), index=True)
    monthly_rent: Mapped[float|None]=mapped_column(Float)
    area_sqm: Mapped[float|None]=mapped_column(Float)
    rent_per_sqm: Mapped[float|None]=mapped_column(Float)
    location_type: Mapped[str|None]=mapped_column(String(100))
    source: Mapped[str]=mapped_column(String(50), default="manual")
    timestamp: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=now)
    confidence: Mapped[float]=mapped_column(Float, default=.5)
    status: Mapped[str]=mapped_column(String(50), default="pending_review")
    raw_data: Mapped[dict[str,Any]]=mapped_column(JSON, default=dict)

class PopulationDataRecord(Base):
    __tablename__="population_data"
    id: Mapped[int]=mapped_column(primary_key=True)
    project_id: Mapped[str|None]=mapped_column(String(80), index=True)
    nearby_university_count: Mapped[int|None]=mapped_column(Integer)
    nearby_school_count: Mapped[int|None]=mapped_column(Integer)
    nearby_apartment_count: Mapped[int|None]=mapped_column(Integer)
    nearby_residential_count: Mapped[int|None]=mapped_column(Integer)
    young_population_indicator: Mapped[float|None]=mapped_column(Float)
    source: Mapped[str]=mapped_column(String(50), default="manual")
    timestamp: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=now)
    confidence: Mapped[float]=mapped_column(Float, default=.5)
    status: Mapped[str]=mapped_column(String(50), default="pending_review")
    raw_data: Mapped[dict[str,Any]]=mapped_column(JSON, default=dict)

class SupplementRecord(Base):
    __tablename__="supplements"
    id: Mapped[int]=mapped_column(primary_key=True)
    project_id: Mapped[str|None]=mapped_column(String(80), index=True)
    target_type: Mapped[str]=mapped_column(String(80), index=True)
    target_id: Mapped[str|None]=mapped_column(String(120))
    field_name: Mapped[str]=mapped_column(String(120))
    value: Mapped[Any|None]=mapped_column(JSON)
    source: Mapped[str]=mapped_column(String(50), default="manual")
    timestamp: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=now)
    confidence: Mapped[float]=mapped_column(Float, default=.5)
    status: Mapped[str]=mapped_column(String(50), default="pending_review")
    raw_data: Mapped[dict[str,Any]]=mapped_column(JSON, default=dict)
    created_time: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=now)

class ManualInputRecord(Base):
    __tablename__="manual_inputs"
    id: Mapped[int]=mapped_column(primary_key=True)
    project_id: Mapped[str]=mapped_column(String(80), index=True)
    target_type: Mapped[str]=mapped_column(String(80), index=True)
    target_id: Mapped[str|None]=mapped_column(String(120), index=True)
    field_name: Mapped[str]=mapped_column(String(120))
    old_value: Mapped[Any|None]=mapped_column(JSON)
    new_value: Mapped[Any|None]=mapped_column(JSON)
    source: Mapped[str]=mapped_column(String(50), default="manual")
    confidence: Mapped[float]=mapped_column(Float, default=.8)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=now)

class SiteScoreRecord(Base):
    __tablename__="site_scores"
    id: Mapped[int]=mapped_column(primary_key=True)
    project_id: Mapped[str]=mapped_column(String(80), index=True)
    total_score: Mapped[float]=mapped_column(Float)
    level: Mapped[str]=mapped_column(String(50))
    dimension_scores: Mapped[dict[str,Any]]=mapped_column(JSON, default=dict)
    advantage_items: Mapped[list[Any]]=mapped_column(JSON, default=list)
    risk_items: Mapped[list[Any]]=mapped_column(JSON, default=list)
    missing_data: Mapped[list[Any]]=mapped_column(JSON, default=list)
    confidence: Mapped[float]=mapped_column(Float, default=.5)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=now)

class AIReportRecord(Base):
    __tablename__="ai_reports"
    id: Mapped[int]=mapped_column(primary_key=True)
    project_id: Mapped[str]=mapped_column(String(80), index=True)
    input_snapshot: Mapped[dict[str,Any]]=mapped_column(JSON, default=dict)
    score_snapshot: Mapped[dict[str,Any]]=mapped_column(JSON, default=dict)
    report_content: Mapped[str]=mapped_column(Text)
    model_name: Mapped[str]=mapped_column(String(100))
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=now)

class AICallLogRecord(Base):
    __tablename__="ai_call_logs"
    id: Mapped[int]=mapped_column(primary_key=True)
    project_id: Mapped[str]=mapped_column(String(80), index=True)
    report_id: Mapped[int|None]=mapped_column(Integer, index=True)
    model_name: Mapped[str]=mapped_column(String(100))
    input_length: Mapped[int]=mapped_column(Integer, default=0)
    output_length: Mapped[int]=mapped_column(Integer, default=0)
    duration_ms: Mapped[int]=mapped_column(Integer, default=0)
    status: Mapped[str]=mapped_column(String(50), default="success")
    error_message: Mapped[str|None]=mapped_column(Text)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=now)

class ChatSessionRecord(Base):
    __tablename__="chat_sessions"
    id: Mapped[int]=mapped_column(primary_key=True)
    project_id: Mapped[str]=mapped_column(String(80), index=True)
    title: Mapped[str|None]=mapped_column(String(200))
    conversation_summary: Mapped[str|None]=mapped_column(Text)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=now, onupdate=now)

class ChatMessageRecord(Base):
    __tablename__="chat_messages"
    id: Mapped[int]=mapped_column(primary_key=True)
    session_id: Mapped[int]=mapped_column(Integer, index=True)
    role: Mapped[str]=mapped_column(String(30))
    content: Mapped[str]=mapped_column(Text)
    references: Mapped[list[Any]]=mapped_column(JSON, default=list)
    simulation: Mapped[dict[str,Any]|None]=mapped_column(JSON)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=now)


class SystemConfigRecord(Base):
    __tablename__ = "system_configs"
    id: Mapped[int] = mapped_column(primary_key=True)
    config_key: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    encrypted_value: Mapped[str] = mapped_column(Text)
    is_secret: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now, onupdate=now
    )


class MemoryItemRecord(Base):
    __tablename__ = "memory_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    scope: Mapped[str] = mapped_column(String(30), index=True)
    memory_type: Mapped[str] = mapped_column(String(50), index=True)
    title: Mapped[str] = mapped_column(String(200))
    content: Mapped[str] = mapped_column(Text)
    tags: Mapped[list[Any]] = mapped_column(JSON, default=list)
    source: Mapped[str] = mapped_column(String(80), default="manual")
    confidence: Mapped[float] = mapped_column(Float, default=.7)
    status: Mapped[str] = mapped_column(String(50), default="pending_review", index=True)
    project_id: Mapped[str | None] = mapped_column(String(80), index=True)
    user_id: Mapped[str | None] = mapped_column(String(80), index=True)
    raw_data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class ScoringDimensionRecord(Base):
    __tablename__ = "scoring_dimensions"
    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text)
    weight: Mapped[float] = mapped_column(Float, default=0)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    data_sources: Mapped[list[Any]] = mapped_column(JSON, default=list)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class ScoringFactorRecord(Base):
    __tablename__ = "scoring_factors"
    id: Mapped[int] = mapped_column(primary_key=True)
    dimension_key: Mapped[str] = mapped_column(String(80), index=True)
    key: Mapped[str] = mapped_column(String(120), index=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text)
    weight: Mapped[float] = mapped_column(Float, default=0)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    data_sources: Mapped[list[Any]] = mapped_column(JSON, default=list)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class CrawlTaskRecord(Base):
    __tablename__ = "crawl_tasks"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[str] = mapped_column(String(80), index=True)
    task_type: Mapped[str] = mapped_column(String(40), index=True)
    target_name: Mapped[str | None] = mapped_column(String(200))
    target_address: Mapped[str | None] = mapped_column(String(300))
    target_url: Mapped[str | None] = mapped_column(Text)
    provider: Mapped[str] = mapped_column(String(80), default="crawl4ai")
    status: Mapped[str] = mapped_column(String(40), default="pending", index=True)
    source_domain: Mapped[str | None] = mapped_column(String(200), index=True)
    input_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    result_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CrawlerFieldSuggestionRecord(Base):
    __tablename__ = "crawler_field_suggestions"
    __table_args__ = (
        UniqueConstraint(
            "task_id", "record_type", "record_id", "field_name", "source_url",
            name="uq_crawler_suggestion_task_record_field_source",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[str] = mapped_column(String(80), index=True)
    task_id: Mapped[int] = mapped_column(Integer, index=True)
    record_type: Mapped[str] = mapped_column(String(40), index=True)
    record_id: Mapped[int | None] = mapped_column(Integer, index=True)
    field_name: Mapped[str] = mapped_column(String(80), index=True)
    suggested_value: Mapped[Any | None] = mapped_column(JSON)
    reviewed_value: Mapped[Any | None] = mapped_column(JSON)
    source_url: Mapped[str] = mapped_column(Text)
    source_domain: Mapped[str | None] = mapped_column(String(200), index=True)
    evidence_excerpt: Mapped[str | None] = mapped_column(Text)
    extraction_method: Mapped[str] = mapped_column(String(40), default="rule_extract")
    confidence: Mapped[float] = mapped_column(Float, default=.6)
    source_quality: Mapped[str] = mapped_column(String(30), default="medium")
    freshness_status: Mapped[str] = mapped_column(String(30), default="unknown")
    conflict_status: Mapped[str] = mapped_column(String(30), default="none")
    status: Mapped[str] = mapped_column(String(30), default="pending_review", index=True)
    review_remark: Mapped[str | None] = mapped_column(Text)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class BusinessOutcomeRecord(Base):
    __tablename__ = "business_outcomes"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    actual_monthly_rent: Mapped[float | None] = mapped_column(Float)
    actual_area_sqm: Mapped[float | None] = mapped_column(Float)
    actual_machine_count: Mapped[int | None] = mapped_column(Integer)
    opening_date: Mapped[date | None] = mapped_column(Date)
    actual_investment: Mapped[float | None] = mapped_column(Float)
    occupancy_rate: Mapped[float | None] = mapped_column(Float)
    result_status: Mapped[str | None] = mapped_column(String(50))
    success_reasons: Mapped[list[Any]] = mapped_column(JSON, default=list)
    failure_reasons: Mapped[list[Any]] = mapped_column(JSON, default=list)
    notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default="pending_review", index=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class RegionalStatisticRecord(Base):
    __tablename__ = "regional_statistics"
    __table_args__ = (
        UniqueConstraint(
            "metric_code",
            "scope_code",
            "stat_period",
            "source_name",
            name="uq_regional_statistics_metric_scope_period_source",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    metric_code: Mapped[str] = mapped_column(String(80), index=True)
    metric_name: Mapped[str] = mapped_column(String(160))
    value_numeric: Mapped[float | None] = mapped_column(Float)
    value_text: Mapped[str | None] = mapped_column(Text)
    unit: Mapped[str | None] = mapped_column(String(40))
    scope_level: Mapped[str] = mapped_column(String(30), index=True)
    scope_code: Mapped[str] = mapped_column(String(40), index=True)
    scope_name: Mapped[str] = mapped_column(String(120), index=True)
    stat_period: Mapped[str] = mapped_column(String(30), index=True)
    source_name: Mapped[str] = mapped_column(String(160))
    source_url: Mapped[str] = mapped_column(Text)
    source_format: Mapped[str] = mapped_column(String(30))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    status: Mapped[str] = mapped_column(String(50), default="pending_review", index=True)
    confidence: Mapped[float] = mapped_column(Float, default=.8)
    raw_data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class DataSyncRunRecord(Base):
    __tablename__ = "data_sync_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    provider: Mapped[str] = mapped_column(String(80), index=True)
    project_id: Mapped[str | None] = mapped_column(String(80), index=True)
    scope_code: Mapped[str | None] = mapped_column(String(40), index=True)
    scope_name: Mapped[str | None] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(40), default="pending", index=True)
    imported_count: Mapped[int] = mapped_column(Integer, default=0)
    pending_review_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)
    input_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    result_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
