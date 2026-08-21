from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.map_data.amap_client import AmapConfigError, AmapMapDataClient, AmapRequestError, poi_identity
from app.map_data.mapper import amap_poi_to_unified
from app.models import SiteProjectRecord, UnifiedPOIRecord
from app.projects.service import get_project


class ProjectNotFoundError(RuntimeError):
    pass


class GeocodeConfirmationRequired(RuntimeError):
    def __init__(self, candidates: list[dict[str, Any]]):
        super().__init__("地址存在多个候选结果，请先确认准确位置")
        self.candidates = candidates


def _column_payload(payload: dict[str, Any]) -> dict[str, Any]:
    columns = UnifiedPOIRecord.__table__.columns.keys()
    return {key: value for key, value in payload.items() if key in columns}


def _normalize(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "")).casefold()


def _payload_identity(payload: dict[str, Any]) -> tuple[Any, ...]:
    raw = payload.get("raw_data") if isinstance(payload.get("raw_data"), dict) else {}
    fields = raw.get("_amap_fields") if isinstance(raw.get("_amap_fields"), dict) else {}
    amap_id = str(fields.get("poi_id") or raw.get("id") or "").strip()
    if amap_id:
        return ("amap_id", amap_id)
    longitude = payload.get("longitude")
    latitude = payload.get("latitude")
    return (
        "fallback",
        _normalize(payload.get("name")),
        _normalize(payload.get("address")),
        round(float(longitude), 6) if longitude is not None else None,
        round(float(latitude), 6) if latitude is not None else None,
    )


def _row_identity(row: UnifiedPOIRecord) -> tuple[Any, ...]:
    return _payload_identity(
        {
            "name": row.name,
            "address": row.address,
            "longitude": row.longitude,
            "latitude": row.latitude,
            "raw_data": row.raw_data,
        }
    )


def _find_existing_poi(db: Session, payload: dict[str, Any]) -> UnifiedPOIRecord | None:
    rows = db.scalars(
        select(UnifiedPOIRecord).where(
            UnifiedPOIRecord.project_id == payload.get("project_id"),
            UnifiedPOIRecord.source == "amap",
        )
    ).all()
    identity = _payload_identity(payload)
    return next((row for row in rows if _row_identity(row) == identity), None)


def _merge_raw_data(existing: Any, incoming: Any) -> dict[str, Any]:
    old = dict(existing) if isinstance(existing, dict) else {}
    new = dict(incoming) if isinstance(incoming, dict) else {}
    protected = {
        key: value
        for key, value in old.items()
        if key in {"manual_detail", "crawler_detail", "demo_detail", "review_history"}
        or key.startswith("manual_")
    }
    return {**new, **protected}


def _upsert_poi(db: Session, payload: dict[str, Any]) -> tuple[UnifiedPOIRecord, bool]:
    existing = _find_existing_poi(db, payload)
    if existing:
        old_raw = existing.raw_data if isinstance(existing.raw_data, dict) else {}
        manual_detail = old_raw.get("manual_detail") if isinstance(old_raw.get("manual_detail"), dict) else {}
        has_manual_business_hours = "business_hours" in manual_detail
        amap_owned_fields = {
            "name",
            "category",
            "sub_category",
            "address",
            "longitude",
            "latitude",
            "distance_meters",
            "walking_distance_meters",
            "timestamp",
        }
        for key in amap_owned_fields:
            if key in payload:
                setattr(existing, key, payload[key])
        if not has_manual_business_hours and payload.get("business_hours"):
            existing.business_hours = payload["business_hours"]
        existing.raw_data = _merge_raw_data(old_raw, payload.get("raw_data"))
        return existing, False
    row = UnifiedPOIRecord(**payload)
    db.add(row)
    return row, True


def _count_collected(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"poi_count": len(rows), "competitor_count": 0, "food_count": 0, "entertainment_count": 0}
    for row in rows:
        category = row.get("category")
        if category == "competitor":
            counts["competitor_count"] += 1
        elif category == "food":
            counts["food_count"] += 1
        elif category == "entertainment":
            counts["entertainment_count"] += 1
    return counts


def _geocode_candidates(data: dict[str, Any]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    geocodes = data.get("geocodes")
    if not isinstance(geocodes, list):
        return candidates
    for index, item in enumerate(geocodes):
        if not isinstance(item, dict):
            continue
        location = str(item.get("location") or "")
        if "," not in location:
            continue
        try:
            longitude, latitude = (float(value) for value in location.split(",", 1))
        except (TypeError, ValueError):
            continue
        candidates.append(
            {
                "index": index,
                "formatted_address": item.get("formatted_address"),
                "province": item.get("province"),
                "city": item.get("city"),
                "district": item.get("district"),
                "level": item.get("level"),
                "longitude": longitude,
                "latitude": latitude,
            }
        )
    return candidates


async def _ensure_project_location(
    db: Session,
    project: SiteProjectRecord,
    amap_client: AmapMapDataClient,
    *,
    force: bool = False,
    candidate_index: int | None = None,
) -> dict[str, Any]:
    if not force and candidate_index is None and project.longitude is not None and project.latitude is not None:
        return {"needed": False}

    geocode_data = await amap_client.geocode(city=project.city, address=project.address)
    candidates = _geocode_candidates(geocode_data)
    if not candidates:
        raise AmapRequestError("no_geocode_result", "高德地址解析没有返回可用坐标")
    if candidate_index is None and len(candidates) > 1:
        raw_data = dict(project.raw_data) if isinstance(project.raw_data, dict) else {}
        raw_data["geocode_candidates"] = candidates
        project.raw_data = raw_data
        db.commit()
        raise GeocodeConfirmationRequired(candidates)
    selected_index = candidate_index if candidate_index is not None else candidates[0]["index"]
    selected = next((item for item in candidates if item["index"] == selected_index), None)
    if selected is None:
        raise AmapRequestError("invalid_candidate", "所选地址候选项无效，请重新选择")

    project.longitude = selected["longitude"]
    project.latitude = selected["latitude"]
    raw_data = dict(project.raw_data) if isinstance(project.raw_data, dict) else {}
    raw_data.pop("geocode_candidates", None)
    raw_data["geocode"] = {
        "source": "amap",
        "formatted_address": selected.get("formatted_address"),
        "level": selected.get("level"),
        "city": selected.get("city"),
        "district": selected.get("district"),
        "candidate_index": selected["index"],
        "auto_filled": candidate_index is None,
    }
    project.raw_data = raw_data
    project.updated_at = datetime.now(timezone.utc)
    db.commit()
    return {
        "needed": True,
        "forced": force,
        "success": True,
        "longitude": project.longitude,
        "latitude": project.latitude,
        "selected_candidate": selected,
    }


async def geocode_project(
    db: Session,
    project_id: str,
    *,
    client: AmapMapDataClient | None = None,
    force: bool = False,
    candidate_index: int | None = None,
) -> dict[str, Any]:
    project: SiteProjectRecord | None = get_project(db, project_id)
    if not project:
        raise ProjectNotFoundError("Project not found")
    amap_client = client or AmapMapDataClient()
    try:
        result = await _ensure_project_location(
            db, project, amap_client, force=force, candidate_index=candidate_index
        )
    except GeocodeConfirmationRequired as exc:
        return {
            "success": False,
            "status": "needs_confirmation",
            "project_id": project.project_id,
            "message": str(exc),
            "candidates": exc.candidates,
            "diagnostics": {"geocode": {"success": False, "reason": "ambiguous"}},
        }
    except AmapConfigError:
        return {
            "success": False,
            "status": "failed",
            "project_id": project.project_id,
            "message": "AMAP_WEB_SERVICE_KEY未配置，无法解析地址",
            "diagnostics": {"geocode": {"success": False, "reason": "not_configured"}},
        }
    except (AmapRequestError, ValueError) as exc:
        return {
            "success": False,
            "status": "failed",
            "project_id": project.project_id,
            "message": f"地址解析失败：{exc}",
            "diagnostics": {"geocode": {"success": False, "reason": getattr(exc, "code", "invalid")}},
        }
    return {
        "success": True,
        "status": "ready",
        "project_id": project.project_id,
        "location": {"longitude": project.longitude, "latitude": project.latitude},
        "already_located": not result.get("needed", False),
        "message": "项目已有经纬度，无需重新解析" if not result.get("needed", False) else "地址解析成功",
        "diagnostics": result,
    }


def _collection_status(rows: list[dict[str, Any]], diagnostics: dict[str, Any]) -> str:
    query_count = int(diagnostics.get("query_count") or len(diagnostics.get("queries") or []))
    failed_count = int(diagnostics.get("failed_query_count") or len(diagnostics.get("failed_keywords") or []))
    if not rows and query_count and failed_count >= query_count:
        return "failed"
    if failed_count:
        return "partial"
    if diagnostics.get("truncated"):
        return "truncated"
    if not rows:
        return "success_zero"
    return "success"


def record_amap_collection_result(
    db: Session,
    project_id: str,
    result: dict[str, Any],
) -> None:
    """持久化最近一次采集结论，用于区分未执行、零结果和失败。"""
    project = get_project(db, project_id)
    if not project:
        return
    diagnostics = result.get("diagnostics") if isinstance(result.get("diagnostics"), dict) else {}
    collected = result.get("collected") if isinstance(result.get("collected"), dict) else {}
    collected_at = result.get("collected_at")
    raw = dict(project.raw_data or {})
    raw["_amap_collection"] = {
        "status": result.get("collection_status") or ("success" if result.get("success") else "failed"),
        "collected_at": collected_at.isoformat() if isinstance(collected_at, datetime) else collected_at,
        "poi_count": int(collected.get("poi_count") or 0),
        "query_count": int(diagnostics.get("query_count") or len(diagnostics.get("queries") or [])),
        "failed_query_count": int(
            diagnostics.get("failed_query_count") or len(diagnostics.get("failed_keywords") or [])
        ),
        "truncated": bool(diagnostics.get("truncated")),
        "message": result.get("message"),
    }
    project.raw_data = raw
    db.commit()


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
    collected_at = datetime.now(timezone.utc)
    try:
        diagnostics["geocode"] = await _ensure_project_location(db, project, amap_client)
    except GeocodeConfirmationRequired as exc:
        return {
            "success": False,
            "collection_status": "needs_confirmation",
            "project_id": project.project_id,
            "collected": _count_collected([]),
            "message": str(exc),
            "collected_at": collected_at,
            "diagnostics": {"geocode": {"reason": "ambiguous", "candidates": exc.candidates}},
        }
    except AmapConfigError:
        return {
            "success": False,
            "collection_status": "failed",
            "project_id": project.project_id,
            "collected": _count_collected([]),
            "message": "AMAP_WEB_SERVICE_KEY未配置",
            "collected_at": collected_at,
            "diagnostics": {"geocode": {"success": False, "reason": "not_configured"}},
        }
    except (AmapRequestError, ValueError) as exc:
        return {
            "success": False,
            "collection_status": "failed",
            "project_id": project.project_id,
            "collected": _count_collected([]),
            "message": f"地址自动定位失败：{exc}",
            "collected_at": collected_at,
            "diagnostics": {"geocode": {"success": False, "reason": getattr(exc, "code", "invalid")}},
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
            "collection_status": "failed",
            "project_id": project.project_id,
            "collected": _count_collected([]),
            "message": "AMAP_WEB_SERVICE_KEY未配置",
            "collected_at": collected_at,
            "diagnostics": diagnostics,
        }
    except AmapRequestError as exc:
        return {
            "success": False,
            "collection_status": "failed",
            "project_id": project.project_id,
            "collected": _count_collected([]),
            "message": str(exc),
            "collected_at": collected_at,
            "diagnostics": {**diagnostics, "request_error": {"code": exc.code}},
        }

    unique_payloads: dict[tuple[Any, ...], dict[str, Any]] = {}
    for raw in raw_rows:
        unified = amap_poi_to_unified(raw, category=raw.get("category"), sub_category=raw.get("sub_category"))
        unified["project_id"] = project.project_id
        unified["timestamp"] = collected_at
        payload = _column_payload(unified)
        unique_payloads[_payload_identity(payload)] = payload

    created_count = 0
    updated_count = 0
    for payload in unique_payloads.values():
        _, created = _upsert_poi(db, payload)
        created_count += int(created)
        updated_count += int(not created)
    db.commit()
    unique_rows = list(unique_payloads.values())
    service_duplicates = max(0, len(raw_rows) - len(unique_rows))
    diagnostics["raw_discovered_count"] = int(diagnostics.get("raw_return_count") or len(raw_rows))
    diagnostics["stored_unique_count"] = len(unique_rows)
    diagnostics["duplicate_count"] = int(diagnostics.get("duplicate_count") or 0) + service_duplicates
    diagnostics["created_count"] = created_count
    diagnostics["updated_count"] = updated_count
    status = _collection_status(unique_rows, diagnostics)
    messages = {
        "success": "高德 POI 采集完成",
        "success_zero": "高德采集完成，但当前范围内未返回有效 POI",
        "partial": "高德 POI 部分采集成功，部分关键词请求失败",
        "truncated": "高德 POI 采集完成，结果已达到配置上限",
        "failed": "高德 POI 采集失败，所有关键词请求均未成功",
    }
    return {
        "success": status != "failed",
        "collection_status": status,
        "project_id": project.project_id,
        "collected": _count_collected(unique_rows),
        "message": messages[status],
        "collected_at": collected_at,
        "diagnostics": diagnostics,
    }
