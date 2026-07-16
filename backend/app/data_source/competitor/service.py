from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.data_source.base import DataSourceRequest, ProviderCallStatus
from app.data_source.registry import DataSourceRegistry, build_default_registry
from app.models import SiteProjectRecord, UnifiedCompetitorRecord
from app.projects.service import get_project


class CompetitorProjectNotFoundError(RuntimeError):
    pass


class CompetitorNotFoundError(RuntimeError):
    pass


def competitor_to_public(row: UnifiedCompetitorRecord) -> dict[str, Any]:
    raw = row.raw_data if isinstance(row.raw_data, dict) else {}
    manual_detail = raw.get("manual_detail") if isinstance(raw.get("manual_detail"), dict) else {}
    return {
        "id": row.id,
        "name": row.name,
        "address": row.address,
        "distance_meters": row.distance_meters,
        "source": row.source,
        "status": row.status,
        "confidence": row.confidence,
        "raw_category": raw.get("sub_category") or raw.get("category") or raw.get("type"),
        "created_at": row.timestamp,
        "area_sqm": row.area_sqm,
        "machine_count": row.machine_count,
        "cpu": row.cpu,
        "gpu": row.gpu,
        "monitor": row.monitor,
        "hour_price": row.hour_price,
        "member_price": row.member_price,
        "business_hours": manual_detail.get("business_hours"),
        "opening_date": row.opening_date,
        "occupancy_rate": row.occupancy_rate,
        "monthly_sales": row.monthly_sales,
        "annual_sales": row.annual_sales,
        "recharge_info": manual_detail.get("recharge_info"),
        "remark": manual_detail.get("remark"),
    }


def list_project_competitors(db: Session, project_id: str) -> list[dict[str, Any]]:
    if not get_project(db, project_id):
        raise CompetitorProjectNotFoundError("Project not found")
    rows = db.scalars(
        select(UnifiedCompetitorRecord).where(
            UnifiedCompetitorRecord.project_id == project_id,
        ).order_by(UnifiedCompetitorRecord.distance_meters.asc(), UnifiedCompetitorRecord.id.asc())
    ).all()
    return [competitor_to_public(row) for row in rows]


def review_project_competitor(
    db: Session,
    project_id: str,
    competitor_id: int,
    status: str,
) -> dict[str, Any]:
    if not get_project(db, project_id):
        raise CompetitorProjectNotFoundError("Project not found")
    row = db.scalar(
        select(UnifiedCompetitorRecord).where(
            UnifiedCompetitorRecord.project_id == project_id,
            UnifiedCompetitorRecord.id == competitor_id,
        )
    )
    if not row:
        raise CompetitorNotFoundError("Competitor not found")
    row.status = status
    db.commit()
    db.refresh(row)
    return competitor_to_public(row)


def get_project_competitor(db: Session, project_id: str, competitor_id: int) -> dict[str, Any]:
    if not get_project(db, project_id):
        raise CompetitorProjectNotFoundError("Project not found")
    row = db.scalar(
        select(UnifiedCompetitorRecord).where(
            UnifiedCompetitorRecord.project_id == project_id,
            UnifiedCompetitorRecord.id == competitor_id,
        )
    )
    if not row:
        raise CompetitorNotFoundError("Competitor not found")
    return competitor_to_public(row)


def update_project_competitor_detail(
    db: Session,
    project_id: str,
    competitor_id: int,
    changes: dict[str, Any],
) -> dict[str, Any]:
    if not get_project(db, project_id):
        raise CompetitorProjectNotFoundError("Project not found")
    row = db.scalar(
        select(UnifiedCompetitorRecord).where(
            UnifiedCompetitorRecord.project_id == project_id,
            UnifiedCompetitorRecord.id == competitor_id,
        )
    )
    if not row:
        raise CompetitorNotFoundError("Competitor not found")

    column_fields = {
        "area_sqm",
        "machine_count",
        "cpu",
        "gpu",
        "monitor",
        "hour_price",
        "member_price",
        "opening_date",
        "occupancy_rate",
        "monthly_sales",
        "annual_sales",
    }
    for field_name in column_fields:
        if field_name in changes:
            setattr(row, field_name, changes[field_name])

    raw_data = dict(row.raw_data or {})
    existing_manual_detail = raw_data.get("manual_detail")
    manual_detail = dict(existing_manual_detail) if isinstance(existing_manual_detail, dict) else {}
    for field_name in ("business_hours", "recharge_info", "remark"):
        if field_name in changes:
            manual_detail[field_name] = changes[field_name]
    raw_data["manual_detail"] = manual_detail
    row.raw_data = raw_data
    db.commit()
    db.refresh(row)
    return competitor_to_public(row)


def _existing_amap_competitor(
    db: Session,
    project_id: str,
    name: str,
    address: str | None,
) -> UnifiedCompetitorRecord | None:
    statement = select(UnifiedCompetitorRecord).where(
        UnifiedCompetitorRecord.project_id == project_id,
        UnifiedCompetitorRecord.source == "amap",
        UnifiedCompetitorRecord.name == name,
    )
    statement = statement.where(
        UnifiedCompetitorRecord.address == address
        if address is not None
        else UnifiedCompetitorRecord.address.is_(None)
    )
    return db.scalar(statement.limit(1))


def _save_competitor(
    db: Session,
    project_id: str,
    item: Any,
) -> tuple[UnifiedCompetitorRecord, bool]:
    existing = _existing_amap_competitor(db, project_id, item.name, item.address)
    payload = item.model_dump(mode="python")
    columns = UnifiedCompetitorRecord.__table__.columns.keys()
    payload = {key: value for key, value in payload.items() if key in columns}
    payload["project_id"] = project_id
    payload["timestamp"] = datetime.now(timezone.utc)
    if existing:
        for key, value in payload.items():
            # 重复采集只更新高德基础信息，不能覆盖用户已经做出的确认结论。
            if key not in {"id", "project_id", "status"}:
                setattr(existing, key, value)
        return existing, False
    row = UnifiedCompetitorRecord(**payload)
    db.add(row)
    return row, True


async def collect_project_competitors(
    db: Session,
    project_id: str,
    *,
    registry: DataSourceRegistry | None = None,
) -> dict[str, Any]:
    project: SiteProjectRecord | None = get_project(db, project_id)
    if not project:
        raise CompetitorProjectNotFoundError("Project not found")

    provider = (registry or build_default_registry()).get("amap_competitor")
    result = await provider.get_competitors(
        DataSourceRequest(
            project_id=project.project_id,
            city=project.city,
            longitude=project.longitude,
            latitude=project.latitude,
            radius_meters=project.radius_meters,
        )
    )
    if result.status == ProviderCallStatus.failed:
        return {
            "success": False,
            "project_id": project.project_id,
            "provider": provider.name,
            "discovered_count": 0,
            "saved_count": 0,
            "created_count": 0,
            "updated_count": 0,
            "message": result.warnings[0] if result.warnings else "竞品采集失败",
        }

    created_count = 0
    updated_count = 0
    for item in result.items:
        _, created = _save_competitor(db, project.project_id, item)
        if created:
            created_count += 1
        else:
            updated_count += 1
    db.commit()
    return {
        "success": True,
        "project_id": project.project_id,
        "provider": provider.name,
        "discovered_count": len(result.items),
        "saved_count": created_count + updated_count,
        "created_count": created_count,
        "updated_count": updated_count,
        "message": "未发现电竞馆相关竞品" if not result.items else "竞品采集完成",
    }
