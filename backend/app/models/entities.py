import enum
from datetime import date, datetime, timezone
from typing import Any
from sqlalchemy import Boolean, Date, DateTime, Enum, Float, ForeignKey, Integer, JSON, String, Text
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
    longitude: Mapped[float]=mapped_column(Float); latitude: Mapped[float]=mapped_column(Float); coordinate_system: Mapped[str]=mapped_column(String(20), default="GCJ02"); distance_m: Mapped[int|None]=mapped_column(Integer); phone: Mapped[str|None]=mapped_column(String(100)); business_hours: Mapped[str|None]=mapped_column(String(200)); business_area: Mapped[str|None]=mapped_column(String(100))
    observed_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=now); fetched_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=now); confidence: Mapped[float]=mapped_column(Float, default=.75); is_estimated: Mapped[bool]=mapped_column(Boolean, default=False); is_manually_verified: Mapped[bool]=mapped_column(Boolean, default=False); needs_verification: Mapped[bool]=mapped_column(Boolean, default=False); raw_data: Mapped[dict[str,Any]]=mapped_column(JSON, default=dict)
    evaluation: Mapped[SiteEvaluation]=relationship(back_populates="pois"); enrichment: Mapped["CompetitorEnrichment|None"]=relationship(cascade="all, delete-orphan", uselist=False, back_populates="poi"); survey_records: Mapped[list["CompetitorSurveyRecord"]]=relationship(cascade="all, delete-orphan", back_populates="poi", order_by="CompetitorSurveyRecord.created_at.desc()")

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
