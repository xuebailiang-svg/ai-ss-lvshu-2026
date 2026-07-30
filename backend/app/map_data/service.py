from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.map_data.amap_client import AmapConfigError, AmapMapDataClient
from app.map_data.mapper import amap_poi_to_unified
from app.models import SiteProjectRecord, UnifiedPOIRecord
from app.projects.service import get_project


class ProjectNotFoundError(RuntimeError):
    pass


def _column_payload(payload: dict[str, Any]) -> dict[str, Any]:
    columns = UnifiedPOIRecord.__table__.columns.keys()
    return {key: value for key, value in payload.items() if key in columns}


def _find_existing_poi(db: Session, payload: dict[str, Any]) -> UnifiedPOIRecord | None:
    return db.scalar(
        select(UnifiedPOIRecord).where(
            UnifiedPOIRecord.project_id == payload.get("project_id"),
            UnifiedPOIRecord.name == payload.get("name"),
            UnifiedPOIRecord.longitude == payload.get("longitude"),
            UnifiedPOIRecord.latitude == payload.get("latitude"),
        )
    )


def _upsert_poi(db: Session, payload: dict[str, Any]) -> UnifiedPOIRecord:
    existing = _find_existing_poi(db, payload)
    if existing:
        for key, value in payload.items():
            if key != "id" and hasattr(existing, key):
                setattr(existing, key, value)
        return existing
    row = UnifiedPOIRecord(**payload)
    db.add(row)
    return row


def _count_collected(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts = {
        "poi_count": len(rows),
        "competitor_count": 0,
        "food_count": 0,
        "entertainment_count": 0,
    }
    for row in rows:
        category = row.get("category")
        if category == "competitor":
            counts["competitor_count"] += 1
        elif category == "food":
            counts["food_count"] += 1
        elif category == "entertainment":
            counts["entertainment_count"] += 1
    return counts


def _extract_geocode_location(data: dict[str, Any]) -> tuple[float, float]:
    geocodes = data.get("geocodes")
    if not isinstance(geocodes, list) or not geocodes:
        raise RuntimeError("高德地址解析没有返回结果")
    first = geocodes[0]
    if not isinstance(first, dict):
        raise RuntimeError("高德地址解析结果格式异常")
    location = str(first.get("location") or "")
    if "," not in location:
        raise RuntimeError("高德地址解析结果缺少经纬度")
    longitude_text, latitude_text = location.split(",", 1)
    return float(longitude_text), float(latitude_text)


async def _ensure_project_location(
    db: Session,
    project: SiteProjectRecord,
    amap_client: AmapMapDataClient,
) -> dict[str, Any]:
    if project.longitude is not None and project.latitude is not None:
        return {"needed": False}

    geocode_data = await amap_client.geocode(city=project.city, address=project.address)
    longitude, latitude = _extract_geocode_location(geocode_data)
    project.longitude = longitude
    project.latitude = latitude
    raw_data = project.raw_data if isinstance(project.raw_data, dict) else {}
    first = (geocode_data.get("geocodes") or [{}])[0]
    raw_data["geocode"] = {
        "source": "amap",
        "formatted_address": first.get("formatted_address") if isinstance(first, dict) else None,
        "auto_filled": True,
    }
    project.raw_data = raw_data
    project.updated_at = datetime.now(timezone.utc)
    db.commit()
    return {
        "needed": True,
        "success": True,
        "longitude": longitude,
        "latitude": latitude,
    }


async def collect_amap_for_project(
    db: Session,
    project_id: str,
    *,
    client: AmapMapDataClient | None = None,
) -> dict[str, Any]:
    project: SiteProjectRecord | None = get_project(db, project_id)
    if not project:
        raise ProjectNotFoundError("Project not found")

    amap_client = client or AmapMapDataClient()
    diagnostics: dict[str, Any] = {}
    try:
        diagnostics["geocode"] = await _ensure_project_location(db, project, amap_client)
    except AmapConfigError:
        return {
            "success": False,
            "project_id": project.project_id,
            "collected": _count_collected([]),
            "message": "AMAP_WEB_SERVICE_KEY未配置，无法自动定位地址",
            "diagnostics": {"geocode": {"success": False, "reason": "not_configured"}},
        }
    except Exception as exc:  # noqa: BLE001 - 返回客户可读错误，不暴露 Key
        return {
            "success": False,
            "project_id": project.project_id,
            "collected": _count_collected([]),
            "message": f"地址自动定位失败：{exc}",
            "diagnostics": {"geocode": {"success": False, "reason": str(exc)}},
        }

    try:
        raw_rows, collect_diagnostics = await amap_client.collect_pois(
            longitude=project.longitude,
            latitude=project.latitude,
            radius_meters=project.radius_meters,
            city=project.city,
        )
        diagnostics.update(collect_diagnostics)
    except AmapConfigError:
        return {
            "success": False,
            "project_id": project.project_id,
            "collected": _count_collected([]),
            "message": "AMAP_WEB_SERVICE_KEY未配置",
            "diagnostics": diagnostics,
        }

    saved_rows: dict[tuple[Any, Any, Any], dict[str, Any]] = {}
    for raw in raw_rows:
        unified = amap_poi_to_unified(
            raw,
            category=raw.get("category"),
            sub_category=raw.get("sub_category"),
        )
        unified["project_id"] = project.project_id
        unified["timestamp"] = datetime.now(timezone.utc)
        payload = _column_payload(unified)
        _upsert_poi(db, payload)
        identity = (
            payload.get("name"),
            payload.get("longitude"),
            payload.get("latitude"),
        )
        saved_rows[identity] = payload
    db.commit()
    unique_rows = list(saved_rows.values())
    diagnostics["raw_discovered_count"] = len(raw_rows)
    diagnostics["stored_unique_count"] = len(unique_rows)
    diagnostics["duplicate_count"] = max(0, len(raw_rows) - len(unique_rows))
    return {
        "success": True,
        "project_id": project.project_id,
        "collected": _count_collected(unique_rows),
        "message": "高德 POI 采集完成",
        "diagnostics": diagnostics,
    }
