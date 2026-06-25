from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.core.database import get_db
from app.models import *
from app.providers.amap import AmapDataProvider, ProviderError
from app.reports.standard import StandardReportRenderer
from app.schemas import ComparisonIn, CompetitorEnrichmentIn, EvaluationCreate, EvaluationOut, PropertyIn
from app.scoring.rule_based import RuleBasedScoringEngine

router = APIRouter(prefix="/api")


def provider():
    settings = get_settings()
    return AmapDataProvider(settings.amap_web_service_key, mock=settings.amap_mock)


def evaluation_options():
    return (
        selectinload(SiteEvaluation.site).selectinload(CandidateSite.property_survey),
        selectinload(SiteEvaluation.pois).selectinload(PoiObservation.enrichment),
        selectinload(SiteEvaluation.pois).selectinload(PoiObservation.survey_records),
        selectinload(SiteEvaluation.result),
    )


def evaluation_or_404(db: Session, id: int):
    ev = db.scalar(select(SiteEvaluation).where(SiteEvaluation.id == id).options(*evaluation_options()))
    if not ev:
        raise HTTPException(404, "Evaluation not found")
    return ev


def poi_or_404(db: Session, id: int):
    poi = db.scalar(
        select(PoiObservation)
        .where(PoiObservation.id == id)
        .options(selectinload(PoiObservation.enrichment), selectinload(PoiObservation.survey_records))
    )
    if not poi:
        raise HTTPException(404, "POI not found")
    return poi


@router.get("/health")
def health(db: Session = Depends(get_db)):
    db.execute(select(1))
    return {"status": "ok", "service": "esports-site-selection", "database": "connected"}


@router.get("/health/config")
def health_config():
    settings = get_settings()
    return {
        "amap_configured": bool(settings.amap_web_service_key),
        "amap_mock": settings.amap_mock,
        "llm_enabled": False,
        "llm_configured": False,
        "provider": None,
        "model": None,
        "note": "M1/M1.5 当前报告为规则评分报告，不调用大模型。",
    }


def mask_secret(value: str | None) -> str | None:
    value = (value or "").strip()
    if not value:
        return None
    if len(value) <= 8:
        return "***"
    return f"{value[:4]}****{value[-4:]}"


def read_frontend_runtime_config() -> dict[str, Any]:
    path = Path(get_settings().frontend_runtime_config_path)
    if not path.exists() or not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"_invalid": True}
    return data if isinstance(data, dict) else {"_invalid": True}


@router.get("/system/runtime-config")
def runtime_config():
    data = read_frontend_runtime_config()
    if data.get("_invalid"):
        return {"amapJsKey": "", "amapSecurityJsCode": "", "mapProvider": "amap", "invalid": True}
    return {
        "amapJsKey": str(data.get("amapJsKey") or ""),
        "amapSecurityJsCode": str(data.get("amapSecurityJsCode") or ""),
        "mapProvider": str(data.get("mapProvider") or "amap"),
    }


@router.get("/system/config-status")
def system_config_status():
    settings = get_settings()
    runtime = read_frontend_runtime_config()
    js_key = "" if runtime.get("_invalid") else str(runtime.get("amapJsKey") or "")
    js_code = "" if runtime.get("_invalid") else str(runtime.get("amapSecurityJsCode") or "")
    return {
        "backend": {
            "amapWebServiceKeyConfigured": bool(settings.amap_web_service_key),
            "amapMock": settings.amap_mock,
            "databaseConfigured": bool(settings.database_url),
        },
        "frontend": {
            "runtimeConfigPath": settings.frontend_runtime_config_path,
            "runtimeConfigExists": bool(runtime) and not runtime.get("_invalid"),
            "runtimeConfigInvalid": bool(runtime.get("_invalid")),
            "amapJsKeyConfigured": bool(js_key),
            "amapSecurityJsCodeConfigured": bool(js_code),
            "amapJsKeyMasked": mask_secret(js_key),
            "mapProvider": str(runtime.get("mapProvider") or "amap") if not runtime.get("_invalid") else "amap",
        },
    }


@router.get("/system/amap/geocode-test")
async def system_amap_geocode_test(city: str = "", address: str = ""):
    if not address.strip():
        raise HTTPException(400, "address is required")
    try:
        data = await provider().geocode(address, city or None)
        return {"ok": True, "result": data}
    except ProviderError as exc:
        raise HTTPException(502, exc.to_dict())


@router.post("/evaluations", response_model=EvaluationOut, status_code=201)
def create_evaluation(body: EvaluationCreate, db: Session = Depends(get_db)):
    ev = SiteEvaluation(name=body.name, city=body.city, address=body.address, radius=body.radius)
    site = CandidateSite()
    site.property_survey = PropertySurvey(**property_payload(body.property))
    ev.site = site
    db.add(ev)
    db.commit()
    return evaluation_or_404(db, ev.id)


@router.get("/evaluations", response_model=list[EvaluationOut])
def list_evaluations(
    city: str | None = None,
    q: str | None = None,
    recommendation: str | None = None,
    has_hard_risk: bool | None = None,
    sort_by: str = Query("created_at", pattern="^(created_at|score|completeness|confidence|updated_at)$"),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    db: Session = Depends(get_db),
):
    stmt = select(SiteEvaluation).options(selectinload(SiteEvaluation.site), selectinload(SiteEvaluation.result))
    if city:
        stmt = stmt.where(SiteEvaluation.city.contains(city))
    if q:
        stmt = stmt.where(SiteEvaluation.address.contains(q))
    rows = list(db.scalars(stmt))
    if recommendation:
        rows = [row for row in rows if row.result and row.result.recommendation == recommendation]
    if has_hard_risk is not None:
        rows = [row for row in rows if bool(row.result and row.result.hard_risks) is has_hard_risk]
    rows.sort(key=lambda row: sort_key(row, sort_by), reverse=(order == "desc"))
    return rows


@router.get("/evaluations/{id}")
def get_evaluation(id: int, db: Session = Depends(get_db)):
    return serialize(evaluation_or_404(db, id))


@router.put("/evaluations/{id}/property")
def update_property(id: int, body: PropertyIn, db: Session = Depends(get_db)):
    ev = evaluation_or_404(db, id)
    if not ev.site:
        ev.site = CandidateSite()
    if not ev.site.property_survey:
        ev.site.property_survey = PropertySurvey()
    payload = property_payload(body)
    for key, value in payload.items():
        setattr(ev.site.property_survey, key, value)
    ev.site.property_survey.updated_at = datetime.now(timezone.utc)
    db.commit()
    return property_dict(ev.site.property_survey)


@router.post("/evaluations/{id}/geocode")
async def geocode(id: int, db: Session = Depends(get_db)):
    ev = evaluation_or_404(db, id)
    ev.status = JobStatus.running
    db.commit()
    try:
        data = await provider().geocode(ev.address, ev.city)
        for key in ("formatted_address", "district", "longitude", "latitude", "coordinate_system", "provider"):
            if key in data:
                setattr(ev.site, key, data[key])
        ev.status = JobStatus.completed
        ev.error_message = None
        db.commit()
        return data
    except ProviderError as exc:
        ev.status = JobStatus.failed
        ev.error_message = exc.message
        db.commit()
        raise HTTPException(502, exc.to_dict())


@router.post("/debug/amap/geocode")
async def debug_amap_geocode(body: dict):
    settings = get_settings()
    if settings.app_env != "development" and not settings.enable_debug_endpoints:
        raise HTTPException(404, "Debug endpoint is disabled")
    try:
        return await provider().geocode_debug(body.get("address", ""), body.get("city"))
    except ProviderError as exc:
        raise HTTPException(502, exc.to_dict())


@router.post("/evaluations/{id}/collect-pois")
async def collect_pois(id: int, db: Session = Depends(get_db)):
    ev = evaluation_or_404(db, id)
    if ev.site.longitude is None:
        raise HTTPException(409, "Please geocode the candidate site first")
    ev.status = JobStatus.running
    db.commit()
    cats = ["网吧", "网咖", "电竞馆", "电竞酒店", "小学", "中学", "幼儿园", "大学", "中职", "技校", "政府机构", "医院", "地铁站", "公交站", "停车场", "住宅小区", "公寓", "宿舍", "写字楼", "商场", "餐饮", "奶茶", "便利店", "KTV", "酒吧", "台球厅", "电影院", "密室逃脱", "酒店", "夜市"]
    try:
        amap_provider = provider()
        rows = await amap_provider.search_nearby(ev.site.longitude, ev.site.latitude, ev.radius, cats)
        existing_enrichment = {poi.provider_record_id: competitor_dict(poi.enrichment) for poi in ev.pois if poi.enrichment}
        existing_records = {poi.provider_record_id: [survey_record_dict(record) for record in poi.survey_records] for poi in ev.pois if poi.survey_records}
        for old in list(ev.pois):
            db.delete(old)
        db.flush()
        for row in rows:
            poi = PoiObservation(evaluation_id=ev.id, **row)
            db.add(poi)
            db.flush()
            if row.get("provider_record_id") in existing_enrichment:
                db.add(CompetitorEnrichment(poi_observation_id=poi.id, **existing_enrichment[row["provider_record_id"]]))
            for record in existing_records.get(row.get("provider_record_id"), []):
                db.add(CompetitorSurveyRecord(
                    poi_observation_id=poi.id,
                    payload=record["payload"],
                    source=record["source"],
                    confidence=record["confidence"],
                    verified_at=record["verified_at"],
                ))
        ev.status = JobStatus.completed
        ev.error_message = None
        db.commit()
        return {
            "status": "completed",
            "count": len(rows),
            "diagnostics": {
                **amap_provider.last_poi_diagnostics,
                "saved_by_category": dict(Counter(row.get("category") or "其他" for row in rows)),
            },
        }
    except ProviderError as exc:
        ev.status = JobStatus.failed
        ev.error_message = exc.message
        db.commit()
        raise HTTPException(502, exc.to_dict())


@router.get("/evaluations/{id}/poi-diagnostics")
def poi_diagnostics(id: int, db: Session = Depends(get_db)):
    ev = evaluation_or_404(db, id)
    rows = list(ev.pois or [])
    provider_counts = Counter(row.source or "unknown" for row in rows)
    category_counts = Counter(row.category or "其他" for row in rows)
    type_counts = Counter(f"{row.source or 'unknown'}:{row.type_code or 'unknown'}" for row in rows)
    query_group_counts = Counter()
    for row in rows:
        raw = row.raw_data if isinstance(row.raw_data, dict) else {}
        query_group_counts[str(raw.get("_query_group") or raw.get("query_group") or "unknown")] += 1
    return {
        "evaluation_id": ev.id,
        "poi_total": len(rows),
        "by_category": dict(category_counts),
        "by_provider": dict(provider_counts),
        "by_provider_typecode": dict(type_counts),
        "by_query_group": dict(query_group_counts),
        "note": "最近一次采集的 raw_return_count 和 filtered_out_count 会在 POST /api/evaluations/{id}/collect-pois 的 diagnostics 中返回；历史采集任务未单独落表。",
    }


@router.post("/evaluations/{id}/score")
def score(id: int, db: Session = Depends(get_db)):
    ev = evaluation_or_404(db, id)
    result = calculate_score(ev)
    if ev.result:
        for key, value in result.items():
            setattr(ev.result, key, value)
        ev.result.created_at = datetime.now(timezone.utc)
    else:
        db.add(ScoringResult(evaluation_id=id, **result))
    db.flush()
    report_data = jsonable_encoder(StandardReportRenderer().render(result, evaluation_payload(ev)))
    existing = db.scalar(select(EvaluationReport).where(EvaluationReport.evaluation_id == id))
    if existing:
        existing.content = report_data
        existing.generated_at = datetime.now(timezone.utc)
    else:
        db.add(EvaluationReport(evaluation_id=id, renderer="standard", content=report_data))
    db.commit()
    return result


@router.get("/evaluations/{id}/report")
def report(id: int, db: Session = Depends(get_db)):
    evaluation_or_404(db, id)
    row = db.scalar(select(EvaluationReport).where(EvaluationReport.evaluation_id == id))
    if not row:
        raise HTTPException(409, "Please score the evaluation first")
    return row.content


@router.put("/competitors/{id}/enrichment")
def enrich(id: int, body: CompetitorEnrichmentIn, db: Session = Depends(get_db)):
    poi = poi_or_404(db, id)
    if poi.category != "竞品":
        raise HTTPException(404, "Competitor POI not found")
    payload = competitor_payload(body)
    row = db.scalar(select(CompetitorEnrichment).where(CompetitorEnrichment.poi_observation_id == id))
    if row:
        for key, value in payload.items():
            setattr(row, key, value)
    else:
        row = CompetitorEnrichment(poi_observation_id=id, **payload)
        db.add(row)
    record = CompetitorSurveyRecord(
        poi_observation_id=id,
        payload=jsonable_encoder(payload),
        source=payload.get("source"),
        confidence=payload.get("confidence") or 0.5,
        verified_at=payload.get("verified_at"),
    )
    poi.is_manually_verified = bool(payload.get("is_manually_verified") or payload.get("verified_at"))
    poi.confidence = max(poi.confidence or 0, payload.get("confidence") or 0.5)
    db.add(record)
    db.commit()
    db.refresh(row)
    return {"id": row.id, "poi_observation_id": id, **competitor_dict(row), "survey_record_id": record.id}


@router.get("/competitors/{id}/enrichments")
def competitor_history(id: int, db: Session = Depends(get_db)):
    poi = poi_or_404(db, id)
    return {
        "poi": poi_dict(poi),
        "latest": competitor_dict(poi.enrichment) if poi.enrichment else None,
        "records": [survey_record_dict(record) for record in poi.survey_records],
    }


@router.post("/evaluations/compare")
def compare(body: ComparisonIn, db: Session = Depends(get_db)):
    rows = [evaluation_or_404(db, id) for id in body.evaluation_ids]
    return {"items": [comparison_item(row) for row in rows]}


@router.get("/regulation-rules")
def rules(db: Session = Depends(get_db)):
    rows = list(db.scalars(select(RegulationRule).where(RegulationRule.enabled == True)))
    if rows:
        return rows
    return [{"city": "*", "sensitive_type": "小学/中学", "limit_distance_m": 200, "calculation_method": "provider_distance", "risk_level": "high", "policy_basis": "示例初筛规则，须以当地现行政策为准", "manual_review": True}]


def calculate_score(ev: SiteEvaluation):
    path = Path(get_settings().scoring_config_path)
    if not path.is_absolute():
        path = Path(__file__).parents[1] / "scoring" / "default.yaml"
    cfg = yaml.safe_load(path.read_text(encoding="utf-8"))
    return RuleBasedScoringEngine().evaluate(
        {"pois": [poi_dict(poi) for poi in ev.pois], "property": property_dict(ev.site.property_survey)},
        cfg,
    )


def property_payload(body: PropertyIn) -> dict[str, Any]:
    payload = body.model_dump()
    area = payload.get("usable_area_sqm") or payload.get("area_sqm")
    monthly = payload.get("monthly_rent")
    per_day = payload.get("rent_per_sqm_day")
    if monthly is None and per_day is not None and area:
        monthly = round(float(per_day) * float(area) * 30, 2)
        payload["monthly_rent"] = monthly
    if per_day is None and monthly is not None and area:
        per_day = round(float(monthly) / float(area) / 30, 2)
        payload["rent_per_sqm_day"] = per_day
    if payload.get("rent_per_sqm_month") is None and monthly is not None and area:
        payload["rent_per_sqm_month"] = round(float(monthly) / float(area), 2)
    if payload.get("rent_per_machine_month") is None and monthly is not None and payload.get("machine_count"):
        payload["rent_per_machine_month"] = round(float(monthly) / int(payload["machine_count"]), 2)
    return payload


def competitor_payload(body: CompetitorEnrichmentIn) -> dict[str, Any]:
    payload = body.model_dump()
    payload["hardware"] = {
        "cpu": payload.get("cpu"),
        "gpu": payload.get("gpu"),
        "monitor_size_inch": payload.get("monitor_size_inch"),
        "monitor_refresh_rate": payload.get("monitor_refresh_rate"),
        **(payload.get("hardware") or {}),
    }
    payload["pricing"] = {
        "normal_price": payload.get("normal_price"),
        "premium_price": payload.get("premium_price"),
        "private_room_price": payload.get("private_room_price"),
        "member_price": payload.get("member_price"),
        "recharge_promotion": payload.get("recharge_promotion"),
        **(payload.get("pricing") or {}),
    }
    payload["occupancy"] = {
        "peak_occupancy_rate": payload.get("peak_occupancy_rate"),
        "offpeak_occupancy_rate": payload.get("offpeak_occupancy_rate"),
        "is_estimated": True,
        **(payload.get("occupancy") or {}),
    }
    return payload


def sort_key(row: SiteEvaluation, sort_by: str):
    if sort_by == "score":
        return row.result.total_score if row.result else -1
    if sort_by == "completeness":
        return row.result.completeness if row.result else -1
    if sort_by == "confidence":
        return row.result.confidence if row.result else -1
    if sort_by == "updated_at":
        return row.updated_at or row.created_at
    return row.created_at


def property_dict(prop):
    if not prop:
        return {}
    return {column.name: getattr(prop, column.name) for column in prop.__table__.columns if column.name not in ("id", "candidate_site_id")}


def competitor_dict(row):
    if not row:
        return None
    return {column.name: getattr(row, column.name) for column in row.__table__.columns if column.name not in ("id", "poi_observation_id")}


def survey_record_dict(row):
    return {"id": row.id, "poi_observation_id": row.poi_observation_id, "payload": row.payload, "source": row.source, "confidence": row.confidence, "verified_at": row.verified_at, "created_at": row.created_at}


def poi_dict(poi):
    data = {column.name: getattr(poi, column.name) for column in poi.__table__.columns if column.name not in ("raw_data",)}
    if poi.enrichment:
        data["enrichment"] = competitor_dict(poi.enrichment)
    data["survey_record_count"] = len(poi.survey_records or [])
    return data


def evaluation_payload(ev):
    return {"evaluation": serialize(ev)}


def serialize(ev):
    return {
        "id": ev.id,
        "name": ev.name,
        "city": ev.city,
        "address": ev.address,
        "radius": ev.radius,
        "status": ev.status,
        "error_message": ev.error_message,
        "created_at": ev.created_at,
        "updated_at": ev.updated_at,
        "site": ({
            "id": ev.site.id,
            "formatted_address": ev.site.formatted_address,
            "district": ev.site.district,
            "longitude": ev.site.longitude,
            "latitude": ev.site.latitude,
            "coordinate_system": ev.site.coordinate_system,
            "provider": ev.site.provider,
            "property": property_dict(ev.site.property_survey),
        } if ev.site else None),
        "pois": [poi_dict(poi) for poi in ev.pois],
        "result": ({column.name: getattr(ev.result, column.name) for column in ev.result.__table__.columns} if ev.result else None),
    }


def comparison_item(ev):
    pois = [poi_dict(poi) for poi in ev.pois]
    competitors = [poi for poi in pois if poi.get("category") == "竞品"]
    strong = [poi for poi in competitors if (poi.get("enrichment") or {}).get("machine_count", 0) >= 80 or (poi.get("enrichment") or {}).get("area_sqm", 0) >= 600]
    prop = property_dict(ev.site.property_survey) if ev.site else {}
    result = ev.result
    dimensions = result.dimensions if result else {}
    return {
        "id": ev.id,
        "name": ev.name,
        "address": ev.address,
        "city": ev.city,
        "total_score": result.total_score if result else None,
        "recommendation": result.recommendation if result else None,
        "hard_risk_count": len(result.hard_risks) if result else 0,
        "competitor_count": len(competitors),
        "strong_competitor_count": len(strong),
        "transport_score": dimensions.get("交通分析"),
        "population_score": dimensions.get("人口代理指标"),
        "commercial_score": dimensions.get("商业配套"),
        "property_score": dimensions.get("物业条件"),
        "completeness": result.completeness if result else None,
        "confidence": result.confidence if result else None,
        "monthly_rent": prop.get("monthly_rent"),
        "rent_per_machine_month": prop.get("rent_per_machine_month"),
        "review_item_count": len(result.review_items) if result else 0,
    }
