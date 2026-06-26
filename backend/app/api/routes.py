from __future__ import annotations

from collections import Counter
import csv
from datetime import datetime, timezone
import io
import json
from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter, Depends, HTTPException, Query, Response
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

BASE_POI_COLUMNS = [
    {"key": "name", "label": "名称"},
    {"key": "business_category", "label": "业务类别"},
    {"key": "subcategory", "label": "细分类"},
    {"key": "address", "label": "地址"},
    {"key": "distance_m", "label": "直线距离"},
    {"key": "walking_distance_m", "label": "步行距离"},
    {"key": "walking_time_min", "label": "步行时间"},
    {"key": "data_source", "label": "数据来源"},
    {"key": "verification_status", "label": "核实状态"},
    {"key": "missing_items_text", "label": "待补充项"},
    {"key": "notes", "label": "备注"},
]

POI_TEMPLATES: dict[str, dict[str, Any]] = {
    "竞品": {
        "export_key": "competitor",
        "sub_label": "细分类",
        "fields": [
            ("opening_years", "开业年限"),
            ("opened_at", "开业时间"),
            ("machine_count", "机器数量"),
            ("area_sqm", "营业面积"),
            ("cpu", "CPU"),
            ("gpu", "显卡"),
            ("memory", "内存"),
            ("monitor_size_inch", "显示器尺寸"),
            ("monitor_refresh_rate", "显示器刷新率"),
            ("normal_price", "普通区价格"),
            ("premium_price", "高配区价格"),
            ("private_room_price", "包间价格"),
            ("member_price", "会员价"),
            ("night_package_price", "夜间包时价格"),
            ("recharge_promotion", "充值活动"),
            ("reservation_rate", "订座率"),
            ("weekday_daytime_occupancy", "工作日白天上座率"),
            ("weekday_evening_occupancy", "工作日晚间上座率"),
            ("weekend_daytime_occupancy", "周末白天上座率"),
            ("weekend_evening_occupancy", "周末晚间上座率"),
            ("street_facing", "是否临街"),
            ("visible_signboard", "门头是否醒目"),
            ("is_chain", "是否连锁"),
            ("decoration_level", "装修档次"),
            ("monthly_sales", "月售"),
            ("annual_sales", "年售"),
            ("review_count", "评论数量"),
            ("online_rating", "线上评分"),
            ("business_hours", "营业时间"),
            ("notes", "备注"),
        ],
        "required_labels": ["开业年限", "机器配置", "订座率", "上座率", "是否临街", "门头是否醒目", "月售", "年售"],
    },
    "住宅": {
        "export_key": "residential",
        "sub_label": "住宅类型",
        "fields": [
            ("residential_type", "住宅类型"),
            ("estimated_population", "估算人口"),
            ("population_distribution", "人口分布"),
            ("young_population_18_35", "18-35岁人口估算"),
            ("young_population_ratio", "年轻人口占比"),
            ("rental_population_ratio", "租住人群占比"),
            ("occupancy_rate", "入住率"),
            ("young_renters_main", "是否年轻租客为主"),
            ("relocation_housing", "是否回迁房"),
            ("is_apartment", "是否公寓"),
            ("urban_village", "是否城中村"),
            ("notes", "备注"),
        ],
        "required_labels": ["人口", "人口分布", "18-35岁人口估算", "年轻人口占比"],
    },
    "交通": {
        "export_key": "traffic",
        "sub_label": "交通类型",
        "fields": [
            ("foot_traffic_level", "人流量等级"),
            ("peak_period", "高峰时段"),
            ("first_service_time", "首班时间"),
            ("last_service_time", "末班时间"),
            ("parking_space_count", "停车位数量"),
            ("parking_fee", "停车费"),
            ("parking_fee_unit", "停车费单位"),
            ("night_parking_supported", "是否支持夜间停车"),
            ("easy_to_fill", "是否容易满位"),
            ("entrance_convenient", "是否距离门店入口方便"),
            ("night_accessible", "夜间是否方便到达"),
            ("has_viaduct_barrier", "是否存在高架阻隔"),
            ("has_railway_barrier", "是否存在铁路阻隔"),
            ("has_river_barrier", "是否存在河流阻隔"),
            ("has_greenbelt_barrier", "是否存在大型绿化带阻隔"),
            ("notes", "备注"),
        ],
        "required_labels": ["步行距离", "步行时间", "人流量"],
    },
    "娱乐": {
        "export_key": "entertainment",
        "sub_label": "细分类",
        "fields": [
            ("opening_years", "开业年限"),
            ("business_hours", "营业时间"),
            ("night_open", "夜间是否营业"),
            ("foot_traffic_level", "人流量等级"),
            ("review_count", "评论数量"),
            ("online_rating", "线上评分"),
            ("consumption_level", "消费水平"),
            ("matches_esports_users", "是否与电竞客群匹配"),
            ("notes", "备注"),
        ],
        "required_labels": ["开业年限", "人流量", "评论数量", "线上评分", "营业时间"],
    },
    "餐饮": {
        "export_key": "food",
        "sub_label": "细分类",
        "fields": [
            ("opening_years", "开业年限"),
            ("business_hours", "营业时间"),
            ("night_open", "是否夜间营业"),
            ("open_24h", "是否24小时营业"),
            ("online_rating", "评分"),
            ("review_count", "评论数量"),
            ("avg_spend", "人均消费"),
            ("foot_traffic_level", "人流量等级"),
            ("suitable_for_esports_users", "是否适合电竞用户"),
            ("notes", "备注"),
        ],
        "required_labels": ["步行距离", "开业年限", "营业时间", "评分", "评论数量"],
    },
    "夜间配套": {
        "export_key": "nightlife",
        "sub_label": "细分类",
        "fields": [
            ("opening_years", "开业年限"),
            ("business_hours", "营业时间"),
            ("night_open", "是否夜间营业"),
            ("open_24h", "是否24小时营业"),
            ("online_rating", "评分"),
            ("review_count", "评论数量"),
            ("avg_spend", "人均消费"),
            ("foot_traffic_level", "人流量等级"),
            ("suitable_for_esports_users", "是否适合电竞用户"),
            ("notes", "备注"),
        ],
        "required_labels": ["步行距离", "开业年限", "营业时间", "评分", "评论数量"],
    },
    "敏感场所": {
        "export_key": "sensitive",
        "sub_label": "敏感场所类型",
        "fields": [
            ("within_200m", "是否200米内"),
            ("needs_onsite_review", "是否需要现场复核"),
            ("review_result", "复核结果"),
            ("notes", "备注"),
        ],
        "required_labels": ["是否200米内", "是否需要现场复核", "复核结果"],
    },
    "物业线索": {
        "export_key": "property",
        "sub_label": "细分类",
        "fields": [("notes", "备注")],
        "required_labels": ["备注"],
    },
    "其他": {
        "export_key": "other",
        "sub_label": "细分类",
        "fields": [("notes", "备注")],
        "required_labels": ["备注"],
    },
}

EXPORT_KEY_TO_CATEGORY = {cfg["export_key"]: name for name, cfg in POI_TEMPLATES.items()}

POI_SUBTYPE_TEMPLATES: dict[str, dict[str, list[str]]] = {
    "交通": {
        "地铁站": ["foot_traffic_level", "peak_period", "first_service_time", "last_service_time", "night_accessible", "has_viaduct_barrier", "has_railway_barrier", "has_river_barrier", "has_greenbelt_barrier", "notes"],
        "公交站": ["foot_traffic_level", "peak_period", "first_service_time", "last_service_time", "night_accessible", "has_viaduct_barrier", "has_railway_barrier", "has_river_barrier", "has_greenbelt_barrier", "notes"],
        "停车场": ["parking_space_count", "parking_fee", "parking_fee_unit", "night_parking_supported", "easy_to_fill", "entrance_convenient", "notes"],
        "停车库": ["parking_space_count", "parking_fee", "parking_fee_unit", "night_parking_supported", "easy_to_fill", "entrance_convenient", "notes"],
    },
}


def provider():
    settings = get_settings()
    return AmapDataProvider(settings.amap_web_service_key, mock=settings.amap_mock)


def evaluation_options():
    return (
        selectinload(SiteEvaluation.site).selectinload(CandidateSite.property_survey),
        selectinload(SiteEvaluation.pois).selectinload(PoiObservation.enrichment),
        selectinload(SiteEvaluation.pois).selectinload(PoiObservation.generic_enrichment),
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
    cats = [
        "网吧", "网咖", "电竞馆", "电竞酒店",
        "小学", "中学", "幼儿园", "政府机构", "医院",
        "地铁站", "地铁", "轨道交通", "地铁出入口",
        "公交站", "公交车站", "公交站牌", "公交枢纽", "客运站",
        "停车场", "停车库", "地下停车场", "路边停车", "充电站",
        "住宅小区", "公寓", "宿舍", "写字楼", "大学", "中职", "技校",
        "商场", "餐饮", "奶茶", "便利店", "酒店", "夜市",
        "KTV", "量贩KTV", "歌厅", "酒吧", "台球", "台球厅",
        "电影院", "影城", "密室逃脱", "剧本杀", "桌游", "棋牌室",
    ]
    try:
        amap_provider = provider()
        rows = await amap_provider.search_nearby(ev.site.longitude, ev.site.latitude, ev.radius, cats)
        manual_poi_count = sum(1 for poi in ev.pois if poi.source == "manual")
        existing_enrichment = {poi.provider_record_id: competitor_dict(poi.enrichment) for poi in ev.pois if poi.source == "amap" and poi.enrichment}
        existing_generic = {poi.provider_record_id: poi_enrichment_dict(poi.generic_enrichment) for poi in ev.pois if poi.source == "amap" and poi.generic_enrichment}
        existing_records = {poi.provider_record_id: [survey_record_dict(record) for record in poi.survey_records] for poi in ev.pois if poi.source == "amap" and poi.survey_records}
        for old in list(ev.pois):
            if old.source == "amap":
                db.delete(old)
        db.flush()
        for row in rows:
            poi = PoiObservation(evaluation_id=ev.id, **row)
            db.add(poi)
            db.flush()
            if row.get("provider_record_id") in existing_enrichment:
                db.add(CompetitorEnrichment(poi_observation_id=poi.id, **existing_enrichment[row["provider_record_id"]]))
            if row.get("provider_record_id") in existing_generic:
                generic = existing_generic[row["provider_record_id"]]
                db.add(PoiEnrichment(
                    poi_observation_id=poi.id,
                    category=generic["category"],
                    payload=generic["payload"],
                    data_source=generic["data_source"],
                    verification_status=generic["verification_status"],
                    is_verified=generic["is_verified"],
                    verified_at=generic["verified_at"],
                ))
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
                "manual_poi_preserved": manual_poi_count,
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


@router.get("/poi/templates")
def poi_templates():
    return {
        "base_columns": BASE_POI_COLUMNS,
        "categories": {
            category: {
                "export_key": cfg["export_key"],
                "sub_label": cfg["sub_label"],
                "fields": [{"key": key, "label": label} for key, label in cfg["fields"]],
                "required_labels": cfg["required_labels"],
                "subtype_templates": POI_SUBTYPE_TEMPLATES.get(category, {}),
            }
            for category, cfg in POI_TEMPLATES.items()
        },
    }


@router.get("/evaluations/{id}/pois")
def evaluation_pois(id: int, db: Session = Depends(get_db)):
    ev = evaluation_or_404(db, id)
    items = sorted_poi_items([poi_public_dict(poi) for poi in ev.pois])
    return {
        "evaluation_id": id,
        "total": len(items),
        "counts": dict(Counter(item["business_category"] for item in items)),
        "statistics": poi_statistics(items),
        "items": items,
    }


@router.post("/evaluations/{id}/pois", status_code=201)
def create_manual_poi(id: int, body: dict[str, Any], db: Session = Depends(get_db)):
    ev = evaluation_or_404(db, id)
    name = str(body.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "名称不能为空")
    business_category = normalize_business_category(body.get("business_category") or body.get("category") or "其他", body.get("subcategory"), name)
    subcategory = str(body.get("subcategory") or "").strip() or business_category
    payload = {
        "walking_distance_m": body.get("walking_distance_m"),
        "walking_time_min": body.get("walking_time_min"),
        "notes": body.get("notes"),
        "subcategory": subcategory,
    }
    payload.update(body.get("payload") or {})
    for key, _label in POI_TEMPLATES.get(business_category, {}).get("fields", []):
        if key in body:
            payload[key] = body.get(key)
    poi = PoiObservation(
        evaluation_id=ev.id,
        source="manual",
        provider_record_id=f"manual-{datetime.now(timezone.utc).timestamp()}",
        name=name,
        category=business_category,
        type_code=None,
        address=clean_optional(body.get("address")),
        longitude=None,
        latitude=None,
        distance_m=parse_int(body.get("distance_m")),
        phone=None,
        business_hours=None,
        business_area=None,
        confidence=0.5,
        is_estimated=True,
        is_manually_verified=str(body.get("verification_status") or "") == "已人工核实",
        needs_verification=str(body.get("verification_status") or "未核实") != "已人工核实",
        raw_data={"manual": True, "subcategory": subcategory},
    )
    db.add(poi)
    db.flush()
    db.add(PoiEnrichment(
        poi_observation_id=poi.id,
        category=business_category,
        payload={key: value for key, value in payload.items() if value not in (None, "")},
        data_source=str(body.get("data_source") or "人工"),
        verification_status=str(body.get("verification_status") or "未核实"),
        is_verified=str(body.get("verification_status") or "") == "已人工核实",
        verified_at=datetime.now(timezone.utc) if str(body.get("verification_status") or "") == "已人工核实" else None,
    ))
    db.commit()
    db.refresh(poi)
    return poi_public_dict(poi_or_404(db, poi.id))


@router.put("/evaluations/{evaluation_id}/pois/{poi_id}/enrichment")
def update_poi_enrichment(evaluation_id: int, poi_id: int, body: dict[str, Any], db: Session = Depends(get_db)):
    poi = poi_in_evaluation_or_404(db, evaluation_id, poi_id)
    payload = dict(body.get("payload") or {})
    for key in ("walking_distance_m", "walking_time_min", "notes", "subcategory"):
        if key in body:
            payload[key] = body.get(key)
    category = normalize_business_category(body.get("business_category") or poi.category, body.get("subcategory"), poi.name)
    verification_status = str(body.get("verification_status") or (poi.generic_enrichment.verification_status if poi.generic_enrichment else "未核实"))
    data_source = str(body.get("data_source") or (poi.generic_enrichment.data_source if poi.generic_enrichment else "manual"))
    row = poi.generic_enrichment
    if row:
        row.category = category
        row.payload = {key: value for key, value in payload.items() if value not in (None, "")}
        row.data_source = data_source
        row.verification_status = verification_status
        row.is_verified = verification_status == "已人工核实"
        row.verified_at = datetime.now(timezone.utc) if row.is_verified and not row.verified_at else row.verified_at
        row.updated_at = datetime.now(timezone.utc)
    else:
        row = PoiEnrichment(
            poi_observation_id=poi.id,
            category=category,
            payload={key: value for key, value in payload.items() if value not in (None, "")},
            data_source=data_source,
            verification_status=verification_status,
            is_verified=verification_status == "已人工核实",
            verified_at=datetime.now(timezone.utc) if verification_status == "已人工核实" else None,
        )
        db.add(row)
    if body.get("name"):
        poi.name = str(body["name"]).strip()
    if "address" in body:
        poi.address = clean_optional(body.get("address"))
    if "distance_m" in body:
        poi.distance_m = parse_int(body.get("distance_m"))
    poi.is_manually_verified = verification_status == "已人工核实"
    poi.needs_verification = verification_status != "已人工核实"
    db.commit()
    return poi_public_dict(poi_in_evaluation_or_404(db, evaluation_id, poi_id))


@router.get("/evaluations/{id}/pois/export")
def export_pois(id: int, category: str = "competitor", db: Session = Depends(get_db)):
    ev = evaluation_or_404(db, id)
    business_category = category_from_export_key(category)
    rows = sorted_poi_items([poi_public_dict(poi) for poi in ev.pois if poi_public_dict(poi)["business_category"] == business_category])
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=export_headers(business_category), extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow(export_row(row, business_category))
    content = "\ufeff" + output.getvalue()
    filename = f"evaluation_{id}_{category}.csv"
    return Response(
        content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/evaluations/{id}/pois/import")
def import_pois(id: int, body: dict[str, Any], db: Session = Depends(get_db)):
    evaluation_or_404(db, id)
    business_category = category_from_export_key(str(body.get("category") or ""))
    csv_text = str(body.get("csv_text") or "")
    if not csv_text.strip():
        raise HTTPException(400, "csv_text 不能为空")
    reader = csv.DictReader(io.StringIO(csv_text.lstrip("\ufeff")))
    if not reader.fieldnames or "poi_id" not in reader.fieldnames:
        raise HTTPException(400, "导入文件缺少 poi_id")
    success = 0
    errors = []
    for row_number, row in enumerate(reader, start=2):
        try:
            poi_id = parse_int(row.get("poi_id"))
            if not poi_id:
                raise ValueError("poi_id 为空或格式错误")
            poi = poi_in_evaluation_or_404(db, id, poi_id)
            public = poi_public_dict(poi)
            if public["business_category"] != business_category:
                raise ValueError(f"分类不匹配：当前 POI 为 {public['business_category']}")
            if row.get("名称"):
                poi.name = str(row["名称"]).strip()
            if "地址" in row:
                poi.address = clean_optional(row.get("地址"))
            if "直线距离" in row:
                poi.distance_m = parse_int(row.get("直线距离"))
            payload = payload_from_csv_row(row, business_category)
            verification_status = row.get("核实状态") or "未核实"
            data_source = row.get("数据来源") or "import"
            update_poi_enrichment_from_payload(db, poi, business_category, payload, verification_status, data_source)
            success += 1
        except HTTPException as exc:
            errors.append({"row": row_number, "reason": str(exc.detail)})
        except Exception as exc:
            errors.append({"row": row_number, "reason": str(exc)})
    db.commit()
    return {"success_count": success, "failed_count": len(errors), "errors": errors}


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


def poi_in_evaluation_or_404(db: Session, evaluation_id: int, poi_id: int):
    poi = db.scalar(
        select(PoiObservation)
        .where(PoiObservation.id == poi_id, PoiObservation.evaluation_id == evaluation_id)
        .options(selectinload(PoiObservation.enrichment), selectinload(PoiObservation.generic_enrichment), selectinload(PoiObservation.survey_records))
    )
    if not poi:
        raise HTTPException(404, "POI 不存在或不属于当前评估")
    return poi


def category_from_export_key(value: str) -> str:
    if value in POI_TEMPLATES:
        return value
    if value in EXPORT_KEY_TO_CATEGORY:
        return EXPORT_KEY_TO_CATEGORY[value]
    raise HTTPException(400, f"无法识别分类：{value}")


def normalize_business_category(category: Any, subcategory: Any = None, name: Any = None) -> str:
    text = f"{category or ''} {subcategory or ''} {name or ''}"
    if any(key in text for key in ["网吧", "网咖", "电竞"]):
        return "竞品"
    if any(key in text for key in ["住宅", "小区", "公寓", "回迁房", "城中村", "写字楼", "大学", "中职", "技校", "宿舍"]):
        return "住宅"
    if any(key in text for key in ["地铁", "公交", "停车", "交通"]):
        return "交通"
    if any(key in text for key in ["KTV", "酒吧", "台球", "电影院", "电影", "密室", "剧本杀"]):
        return "娱乐"
    if any(key in text for key in ["夜市", "烧烤", "夜间"]):
        return "夜间配套"
    if any(key in text for key in ["餐饮", "餐馆", "餐厅", "饭店", "奶茶", "便利店", "火锅", "小吃", "商业配套"]):
        return "餐饮"
    if any(key in text for key in ["小学", "中学", "幼儿园", "政府", "医院", "敏感"]):
        return "敏感场所"
    if str(category or "") in POI_TEMPLATES:
        return str(category)
    return "其他"


def infer_subcategory(poi) -> str:
    raw = poi.raw_data if isinstance(poi.raw_data, dict) else {}
    if raw.get("subcategory"):
        return str(raw["subcategory"])
    if poi.generic_enrichment and (poi.generic_enrichment.payload or {}).get("subcategory"):
        return str(poi.generic_enrichment.payload["subcategory"])
    text = f"{poi.name or ''} {poi.category or ''}"
    for key in [
        "电竞酒店", "网咖", "网吧", "电竞馆",
        "住宅小区", "青年公寓", "公寓", "写字楼", "大学", "中职", "技校",
        "地铁出入口", "地铁站", "轨道交通", "公交枢纽", "公交车站", "公交站牌", "公交站", "客运站", "地下停车场", "停车库", "停车场", "充电站",
        "量贩KTV", "KTV", "歌厅", "酒吧", "台球厅", "台球", "电影院", "影城", "密室逃脱", "密室", "剧本杀", "桌游", "棋牌室",
        "夜市摊", "烧烤", "火锅", "便利店", "奶茶", "餐馆", "餐厅",
        "小学", "中学", "幼儿园", "政府机构", "医院",
    ]:
        if key in text:
            return key
    return poi.category or "其他"


def clean_optional(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def parse_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(str(value).replace("m", "").replace("米", "").strip()))
    except ValueError:
        return None


def parse_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace("%", "").strip())
    except ValueError:
        return None


def distance_sort_key(row: dict[str, Any]):
    distance = parse_int(row.get("distance_m"))
    return (distance is None, distance if distance is not None else 10**12, str(row.get("name") or ""))


def sorted_poi_items(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(rows, key=distance_sort_key)


def poi_statistics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    rows = sorted_poi_items(rows)

    def by_category(category: str):
        return [row for row in rows if row.get("business_category") == category]

    def by_categories(*categories: str):
        wanted = set(categories)
        return [row for row in rows if row.get("business_category") in wanted]

    def within(items, meters: int):
        return sum(1 for row in items if (dist := parse_int(row.get("distance_m"))) is not None and dist <= meters)

    def subtype_contains(items, *keywords: str):
        return [row for row in items if any(keyword in f"{row.get('subcategory') or ''} {row.get('name') or ''}" for keyword in keywords)]

    def supplement_value(row, key: str):
        return (row.get("supplement") or {}).get(key)

    def known_count(items, key: str):
        return sum(1 for row in items if supplement_value(row, key) not in (None, "", [], {}))

    def bool_count(items, key: str, accepted=("是", "true", "True", True)):
        return sum(1 for row in items if supplement_value(row, key) in accepted)

    competitors = by_category("竞品")
    food = by_categories("餐饮", "夜间配套")
    entertainment = by_category("娱乐")
    traffic = by_category("交通")
    sensitive = by_category("敏感场所")
    metro = subtype_contains(traffic, "地铁", "轨道交通")
    bus = subtype_contains(traffic, "公交", "客运")
    parking = subtype_contains(traffic, "停车", "停车库")
    schools = subtype_contains(sensitive, "小学", "中学", "幼儿园", "学校")
    government = subtype_contains(sensitive, "政府", "机关", "政务")

    food_opening_years = [parse_float(supplement_value(row, "opening_years")) for row in food]
    food_opening_years = [value for value in food_opening_years if value is not None]
    food_ratings = [parse_float(supplement_value(row, "online_rating")) for row in food]
    food_ratings = [value for value in food_ratings if value is not None]

    return {
        "竞品": {
            "500米内竞品数量": within(competitors, 500),
            "1公里内竞品数量": within(competitors, 1000),
            "2公里内竞品数量": within(competitors, 2000),
            "3公里内竞品数量": within(competitors, 3000),
            "已补充机器数量的竞品数量": known_count(competitors, "machine_count"),
            "已补充上座率的竞品数量": sum(1 for row in competitors if any(supplement_value(row, key) not in (None, "", [], {}) for key in ("peak_occupancy_rate", "weekday_daytime_occupancy", "weekday_evening_occupancy", "weekend_daytime_occupancy", "weekend_evening_occupancy"))),
            "电竞酒店数量": len(subtype_contains(competitors, "电竞酒店")),
            "网咖/电竞馆数量": len(subtype_contains(competitors, "网咖", "电竞馆", "网吧")),
        },
        "餐饮/夜间配套": {
            "500米内餐饮数量": within(food, 500),
            "1公里内餐饮数量": within(food, 1000),
            "夜间营业数量": bool_count(food, "night_open"),
            "24小时营业数量": bool_count(food, "open_24h"),
            "开业年限已补充数量": len(food_opening_years),
            "开业年限大于5年数量": sum(1 for value in food_opening_years if value > 5),
            "开业年限大于10年数量": sum(1 for value in food_opening_years if value > 10),
            "评分已补充数量": len(food_ratings),
            "评分大于等于4.5数量": sum(1 for value in food_ratings if value >= 4.5),
            "便利店数量": len(subtype_contains(food, "便利店")),
            "夜市摊/烧烤/火锅数量": len(subtype_contains(food, "夜市", "烧烤", "火锅")),
        },
        "娱乐": {
            "1公里内娱乐POI数量": within(entertainment, 1000),
            "KTV数量": len(subtype_contains(entertainment, "KTV", "歌厅")),
            "台球厅数量": len(subtype_contains(entertainment, "台球")),
            "电影院数量": len(subtype_contains(entertainment, "电影院", "影城")),
            "酒吧数量": len(subtype_contains(entertainment, "酒吧")),
            "夜间营业数量": bool_count(entertainment, "night_open"),
            "评论数量已补充的数量": known_count(entertainment, "review_count"),
        },
        "交通": {
            "500米内地铁站数量": within(metro, 500),
            "500米内公交站数量": within(bus, 500),
            "1公里内公交站数量": within(bus, 1000),
            "500米内停车场数量": within(parking, 500),
            "已补充步行距离的交通POI数量": known_count(traffic, "walking_distance_m"),
        },
        "敏感场所": {
            "200米内学校/幼儿园数量": within(schools, 200),
            "500米内学校/幼儿园数量": within(schools, 500),
            "200米内政府机构数量": within(government, 200),
            "需要现场复核数量": sum(1 for row in sensitive if row.get("verification_status") != "已人工核实" or supplement_value(row, "needs_onsite_review") in ("是", True)),
        },
    }


def merge_poi_payload(poi) -> dict[str, Any]:
    payload = {}
    if poi.enrichment:
        enrichment = competitor_dict(poi.enrichment) or {}
        payload.update({key: value for key, value in enrichment.items() if value not in (None, "", {}, [])})
        if enrichment.get("recharge_promotion"):
            payload["recharge_promotion"] = enrichment["recharge_promotion"]
    if poi.generic_enrichment:
        payload.update(poi.generic_enrichment.payload or {})
    if poi.business_hours and "business_hours" not in payload:
        payload["business_hours"] = poi.business_hours
    return payload


def missing_items_for(category: str, payload: dict[str, Any]) -> list[str]:
    if category == "竞品":
        checks = {
            "开业年限": ["opening_years", "opened_at", "opened_at_estimate"],
            "机器配置": ["cpu", "gpu", "memory"],
            "订座率": ["reservation_rate"],
            "上座率": ["weekday_daytime_occupancy", "weekday_evening_occupancy", "weekend_daytime_occupancy", "weekend_evening_occupancy", "peak_occupancy_rate"],
            "是否临街": ["street_facing"],
            "门头是否醒目": ["visible_signboard"],
            "月售": ["monthly_sales"],
            "年售": ["annual_sales"],
        }
    elif category == "住宅":
        checks = {"人口": ["estimated_population"], "人口分布": ["population_distribution"], "18-35岁人口估算": ["young_population_18_35"], "年轻人口占比": ["young_population_ratio"]}
    elif category == "交通":
        checks = {"步行距离": ["walking_distance_m"], "步行时间": ["walking_time_min"], "人流量": ["foot_traffic_level"]}
    elif category == "娱乐":
        checks = {"开业年限": ["opening_years"], "人流量": ["foot_traffic_level"], "评论数量": ["review_count"], "线上评分": ["online_rating"], "营业时间": ["business_hours"]}
    elif category in {"餐饮", "夜间配套"}:
        checks = {"步行距离": ["walking_distance_m"], "开业年限": ["opening_years"], "营业时间": ["business_hours"], "评分": ["online_rating"], "评论数量": ["review_count"]}
    elif category == "敏感场所":
        checks = {"是否200米内": ["within_200m"], "是否需要现场复核": ["needs_onsite_review"], "复核结果": ["review_result"]}
    else:
        checks = {"备注": ["notes"]}
    missing = [label for label, keys in checks.items() if not any(payload.get(key) not in (None, "", [], {}) for key in keys)]
    return missing


def poi_enrichment_dict(row):
    if not row:
        return None
    return {
        "category": row.category,
        "payload": row.payload or {},
        "data_source": row.data_source,
        "verification_status": row.verification_status,
        "is_verified": row.is_verified,
        "verified_at": row.verified_at,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def poi_public_dict(poi):
    business_category = normalize_business_category(poi.generic_enrichment.category if poi.generic_enrichment else poi.category, infer_subcategory(poi), poi.name)
    payload = merge_poi_payload(poi)
    payload.setdefault("subcategory", infer_subcategory(poi))
    walking_distance = parse_int(payload.get("walking_distance_m"))
    walking_time = parse_int(payload.get("walking_time_min"))
    verification_status = poi.generic_enrichment.verification_status if poi.generic_enrichment else ("已人工核实" if poi.is_manually_verified else "未核实")
    data_source = poi.generic_enrichment.data_source if poi.generic_enrichment else ("高德" if poi.source == "amap" else "人工")
    missing = missing_items_for(business_category, payload)
    return {
        "poi_id": poi.id,
        "id": poi.id,
        "name": poi.name,
        "business_category": business_category,
        "subcategory": payload.get("subcategory") or infer_subcategory(poi),
        "address": poi.address,
        "distance_m": poi.distance_m,
        "walking_distance_m": walking_distance,
        "walking_time_min": walking_time,
        "data_source": data_source,
        "verification_status": verification_status,
        "missing_items": missing,
        "missing_items_text": "资料较完整" if not missing else "待补充：" + "、".join(missing),
        "notes": payload.get("notes"),
        "supplement": payload,
        "is_manual": poi.source == "manual",
    }


def export_headers(category: str) -> list[str]:
    cfg = POI_TEMPLATES[category]
    headers = ["poi_id", "名称", "业务类别", cfg["sub_label"], "地址", "直线距离", "步行距离", "步行时间", "数据来源", "核实状态", "待补充项", "备注"]
    for _, label in cfg["fields"]:
        if label not in headers:
            headers.append(label)
    return headers


def export_row(row: dict[str, Any], category: str) -> dict[str, Any]:
    cfg = POI_TEMPLATES[category]
    out = {
        "poi_id": row["poi_id"],
        "名称": row["name"],
        "业务类别": row["business_category"],
        cfg["sub_label"]: row["subcategory"],
        "地址": row.get("address"),
        "直线距离": row.get("distance_m"),
        "步行距离": row.get("walking_distance_m"),
        "步行时间": row.get("walking_time_min"),
        "数据来源": row.get("data_source"),
        "核实状态": row.get("verification_status"),
        "待补充项": row.get("missing_items_text"),
        "备注": row.get("notes"),
    }
    supplement = row.get("supplement") or {}
    for key, label in cfg["fields"]:
        out[label] = supplement.get(key)
    return out


def payload_from_csv_row(row: dict[str, Any], category: str) -> dict[str, Any]:
    cfg = POI_TEMPLATES[category]
    payload = {
        "walking_distance_m": row.get("步行距离"),
        "walking_time_min": row.get("步行时间"),
        "notes": row.get("备注"),
        "subcategory": row.get(cfg["sub_label"]),
    }
    for key, label in cfg["fields"]:
        if label in row:
            payload[key] = row.get(label)
    return {key: value for key, value in payload.items() if value not in (None, "")}


def update_poi_enrichment_from_payload(db: Session, poi, category: str, payload: dict[str, Any], verification_status: str, data_source: str):
    row = poi.generic_enrichment
    if row:
        existing = dict(row.payload or {})
        existing.update({key: value for key, value in payload.items() if value not in (None, "")})
        row.payload = existing
        row.category = category
        row.data_source = data_source
        row.verification_status = verification_status
        row.is_verified = verification_status == "已人工核实"
        row.verified_at = datetime.now(timezone.utc) if row.is_verified and not row.verified_at else row.verified_at
        row.updated_at = datetime.now(timezone.utc)
    else:
        row = PoiEnrichment(
            poi_observation_id=poi.id,
            category=category,
            payload={key: value for key, value in payload.items() if value not in (None, "")},
            data_source=data_source,
            verification_status=verification_status,
            is_verified=verification_status == "已人工核实",
            verified_at=datetime.now(timezone.utc) if verification_status == "已人工核实" else None,
        )
        db.add(row)
    poi.is_manually_verified = verification_status == "已人工核实"
    poi.needs_verification = verification_status != "已人工核实"


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
    if poi.generic_enrichment:
        data["generic_enrichment"] = poi_enrichment_dict(poi.generic_enrichment)
    data["public"] = poi_public_dict(poi)
    data["survey_record_count"] = len(poi.survey_records or [])
    return data


def evaluation_payload(ev):
    return {"evaluation": serialize(ev)}


def serialize(ev):
    public_pois = sorted_poi_items([poi_public_dict(poi) for poi in ev.pois])
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
        "poi_statistics": poi_statistics(public_pois),
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
