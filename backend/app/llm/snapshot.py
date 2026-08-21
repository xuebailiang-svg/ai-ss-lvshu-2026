from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.data_quality.service import build_readiness
from app.manual_input.audit import manual_meta
from app.models import (
    EntertainmentRecord,
    FoodBusinessRecord,
    RentDataRecord,
    SiteProjectRecord,
    SupplementRecord,
    UnifiedCompetitorRecord,
    UnifiedPOIRecord,
)
from app.projects.service import get_project


SNAPSHOT_VERSION = "final-project-snapshot-v1"
SOURCE_AMAP = "AMAP_PROVIDED"
SOURCE_USER = "USER_PROVIDED"
SOURCE_CALCULATED = "CALCULATED"
SOURCE_UNKNOWN = "UNKNOWN"


class SnapshotProjectNotFoundError(RuntimeError):
    pass


def _fact(value: Any, source: str) -> dict[str, Any]:
    return {"value": value, "source": source}


def _field_fact(row: Any, field_name: str, *, amap_default: bool = False) -> dict[str, Any] | None:
    meta = manual_meta(getattr(row, "raw_data", None))
    unknown = set(meta.get("unknown_fields") or [])
    if field_name in unknown:
        return _fact(None, SOURCE_UNKNOWN)
    value = getattr(row, field_name, None)
    if value in (None, ""):
        return None
    field_sources = dict(meta.get("field_sources") or {})
    if field_sources.get(field_name) == "manual":
        return _fact(value, SOURCE_USER)
    if getattr(row, "source", None) == "manual":
        return _fact(value, SOURCE_USER)
    if amap_default and getattr(row, "source", None) == "amap":
        return _fact(value, SOURCE_AMAP)
    return None


def _manual_detail_fact(row: Any, field_name: str) -> dict[str, Any] | None:
    raw = row.raw_data if isinstance(getattr(row, "raw_data", None), dict) else {}
    detail = raw.get("manual_detail") if isinstance(raw.get("manual_detail"), dict) else {}
    meta = manual_meta(raw)
    if field_name in set(meta.get("unknown_fields") or []):
        return _fact(None, SOURCE_UNKNOWN)
    value = detail.get(field_name)
    if value in (None, ""):
        return None
    if dict(meta.get("field_sources") or {}).get(field_name) == "manual" or getattr(row, "source", None) == "manual":
        return _fact(value, SOURCE_USER)
    return None


def _compact(values: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in values.items() if value is not None}


def _poi_item(row: UnifiedPOIRecord) -> dict[str, Any]:
    return _compact(
        {
            "name": _fact(row.name, SOURCE_AMAP),
            "category": _fact(row.category, SOURCE_AMAP),
            "sub_category": _fact(row.sub_category, SOURCE_AMAP) if row.sub_category else None,
            "address": _fact(row.address, SOURCE_AMAP) if row.address else None,
            "distance_meters": _fact(row.distance_meters, SOURCE_AMAP) if row.distance_meters is not None else None,
        }
    )


def _competitor_item(row: UnifiedCompetitorRecord) -> dict[str, Any]:
    item: dict[str, Any] = {
        "name": _field_fact(row, "name", amap_default=True),
        "address": _field_fact(row, "address", amap_default=True),
        "distance_meters": _field_fact(row, "distance_meters", amap_default=True),
        "verification": _fact("人工已确认" if row.status == "confirmed" else "高德疑似竞品", SOURCE_CALCULATED),
    }
    if row.status == "confirmed":
        for field in ("area_sqm", "machine_count", "cpu", "gpu", "monitor", "hour_price", "member_price", "occupancy_rate"):
            item[field] = _field_fact(row, field)
    return _compact(item)


def _support_item(row: Any, kind: str) -> dict[str, Any]:
    item = {
        "kind": _fact(kind, SOURCE_CALCULATED),
        "name": _field_fact(row, "name", amap_default=True),
        "distance_meters": _field_fact(row, "distance_meters", amap_default=True),
        "verification": _fact("人工已确认" if row.status == "confirmed" else "高德候选", SOURCE_CALCULATED),
    }
    if row.status == "confirmed":
        for field in ("business_hours", "night_operation", "is_24_hours"):
            item[field] = _manual_detail_fact(row, field)
    return _compact(item)


def _property_snapshot(db: Session, project_id: str) -> dict[str, Any]:
    row = db.scalar(
        select(SupplementRecord).where(
            SupplementRecord.project_id == project_id,
            SupplementRecord.target_type == "candidate_property",
            SupplementRecord.field_name == "manual_detail",
            SupplementRecord.status == "confirmed",
        ).order_by(SupplementRecord.id.desc())
    )
    values = dict(row.value) if row and isinstance(row.value, dict) else {}
    meta = manual_meta(row.raw_data) if row else {}
    unknown = set(meta.get("unknown_fields") or [])
    fields: dict[str, Any] = {}
    for field in (
        "address", "area_sqm", "monthly_rent", "property_fee", "transfer_fee", "floor",
        "use_allowed", "power_capacity_kw", "power_expansion_allowed", "network_carriers",
        "dual_line_supported", "fire_confirmed", "sprinkler", "smoke_exhaust", "safety_exit_count",
    ):
        if field in unknown:
            fields[field] = _fact(None, SOURCE_UNKNOWN)
        elif values.get(field) not in (None, ""):
            fields[field] = _fact(values[field], SOURCE_USER)
    if fields:
        return fields
    rent = db.scalar(
        select(RentDataRecord).where(
            RentDataRecord.project_id == project_id,
            RentDataRecord.status == "confirmed",
            RentDataRecord.source == "manual",
        ).order_by(RentDataRecord.timestamp.desc(), RentDataRecord.id.desc())
    )
    if not rent:
        return {}
    return _compact(
        {
            "address": _field_fact(rent, "location_type"),
            "area_sqm": _field_fact(rent, "area_sqm"),
            "monthly_rent": _field_fact(rent, "monthly_rent"),
            "rent_per_sqm": _field_fact(rent, "rent_per_sqm"),
        }
    )


def _readiness_snapshot(readiness: dict[str, Any]) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for group, items in (readiness.get("groups") or {}).items():
        groups[group] = [
            {key: item.get(key) for key in ("label", "status", "summary", "action") if item.get(key) is not None}
            for item in items
        ]
    return {
        "status": readiness.get("status"),
        "formal_report_ready": bool(readiness.get("formal_report_ready")),
        "completion_percent": _fact(readiness.get("completion_percent"), SOURCE_CALCULATED),
        "groups": groups,
        "warnings": list(readiness.get("warnings") or []),
    }


def build_final_project_snapshot(db: Session, project_id: str) -> dict[str, Any]:
    project = get_project(db, project_id)
    if not project:
        raise SnapshotProjectNotFoundError("Project not found")
    pois = list(
        db.scalars(
            select(UnifiedPOIRecord).where(
                UnifiedPOIRecord.project_id == project_id,
                UnifiedPOIRecord.source == "amap",
                UnifiedPOIRecord.status != "rejected",
            ).order_by(UnifiedPOIRecord.id.asc())
        ).all()
    )
    competitors = list(
        db.scalars(
            select(UnifiedCompetitorRecord).where(
                UnifiedCompetitorRecord.project_id == project_id,
                UnifiedCompetitorRecord.status != "rejected",
                UnifiedCompetitorRecord.source.in_(("amap", "manual")),
            ).order_by(UnifiedCompetitorRecord.distance_meters.asc().nullslast(), UnifiedCompetitorRecord.id.asc())
        ).all()
    )
    food = list(
        db.scalars(
            select(FoodBusinessRecord).where(
                FoodBusinessRecord.project_id == project_id,
                FoodBusinessRecord.status != "rejected",
                FoodBusinessRecord.source.in_(("amap", "manual")),
            ).order_by(FoodBusinessRecord.id.asc())
        ).all()
    )
    entertainment = list(
        db.scalars(
            select(EntertainmentRecord).where(
                EntertainmentRecord.project_id == project_id,
                EntertainmentRecord.status != "rejected",
                EntertainmentRecord.source.in_(("amap", "manual")),
            ).order_by(EntertainmentRecord.id.asc())
        ).all()
    )
    readiness = build_readiness(db, project)
    category_counts = {
        category: _fact(sum(row.category == category for row in pois), SOURCE_CALCULATED)
        for category in ("transport", "competitor", "education", "residential", "food", "entertainment")
    }
    return {
        "snapshot_version": SNAPSHOT_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project": {
            "project_id": project.project_id,
            "name": _fact(project.project_name, SOURCE_USER),
            "business_type": _fact(project.business_type, SOURCE_USER),
            "location": {
                "city": _fact(project.city, SOURCE_USER),
                "district": _fact(project.district, SOURCE_USER) if project.district else None,
                "address": _fact(project.address, SOURCE_USER),
                "longitude": _fact(project.longitude, SOURCE_USER) if project.longitude is not None else _fact(None, SOURCE_UNKNOWN),
                "latitude": _fact(project.latitude, SOURCE_USER) if project.latitude is not None else _fact(None, SOURCE_UNKNOWN),
                "radius_meters": _fact(project.radius_meters, SOURCE_USER),
                "radius_kilometers": _fact(round(project.radius_meters / 1000, 3), SOURCE_CALCULATED),
            },
        },
        "amap_facts": {
            "poi_count": _fact(len(pois), SOURCE_CALCULATED),
            "category_counts": category_counts,
            "pois": [_poi_item(row) for row in pois],
            "boundary": "高德 POI 是本次查询的地点候选和距离事实，不等同于真实客流、消费能力或持续营业状态。",
        },
        "competitors": {
            "candidate_count": _fact(len(competitors), SOURCE_CALCULATED),
            "confirmed_count": _fact(sum(row.status == "confirmed" for row in competitors), SOURCE_CALCULATED),
            "items": [_competitor_item(row) for row in competitors],
        },
        "supporting": {
            "food_candidate_count": _fact(len(food), SOURCE_CALCULATED),
            "entertainment_candidate_count": _fact(len(entertainment), SOURCE_CALCULATED),
            "items": [*[_support_item(row, "餐饮") for row in food], *[_support_item(row, "娱乐") for row in entertainment]],
        },
        "candidate_property": _property_snapshot(db, project_id),
        "data_readiness": _readiness_snapshot(readiness),
        "allowed_conclusion": "数据不足" if not readiness.get("formal_report_ready") else "推荐 / 谨慎 / 不推荐",
        "source_legend": {
            SOURCE_AMAP: "高德采集事实",
            SOURCE_USER: "用户人工提供并保存的事实",
            SOURCE_CALCULATED: "由当前快照确定性计算",
            SOURCE_UNKNOWN: "用户明确不知道或当前缺失",
        },
    }


def snapshot_contains_forbidden_sections(snapshot: dict[str, Any]) -> bool:
    forbidden = {"raw_data", "confidence", "crawler", "government", "memory", "simulation", "score_result", "city_insight"}

    def walk(value: Any) -> bool:
        if isinstance(value, dict):
            return any(str(key).lower() in forbidden or walk(item) for key, item in value.items())
        if isinstance(value, list):
            return any(walk(item) for item in value)
        return False

    return walk(snapshot)
