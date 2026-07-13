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


async def collect_amap_for_project(
    db: Session,
    project_id: str,
    *,
    client: AmapMapDataClient | None = None,
) -> dict[str, Any]:
    project: SiteProjectRecord | None = get_project(db, project_id)
    if not project:
        raise ProjectNotFoundError("Project not found")
    if project.longitude is None or project.latitude is None:
        return {
            "success": False,
            "project_id": project.project_id,
            "collected": _count_collected([]),
            "message": "项目缺少经纬度，无法采集高德POI",
            "diagnostics": {},
        }

    amap_client = client or AmapMapDataClient()
    try:
        raw_rows, diagnostics = await amap_client.collect_pois(
            longitude=project.longitude,
            latitude=project.latitude,
            radius_meters=project.radius_meters,
            city=project.city,
        )
    except AmapConfigError:
        return {
            "success": False,
            "project_id": project.project_id,
            "collected": _count_collected([]),
            "message": "AMAP_WEB_SERVICE_KEY未配置",
            "diagnostics": {},
        }

    saved_rows: list[dict[str, Any]] = []
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
        saved_rows.append(payload)
    db.commit()
    return {
        "success": True,
        "project_id": project.project_id,
        "collected": _count_collected(saved_rows),
        "message": None,
        "diagnostics": diagnostics,
    }
