from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.data_source.base import DataSourceRequest, ProviderCallStatus
from app.data_source.registry import DataSourceRegistry, build_default_registry
from app.manual_input.audit import apply_manual_changes, manual_meta_public
from app.models import EntertainmentRecord, FoodBusinessRecord, SiteProjectRecord
from app.projects.service import get_project


class SupportingProjectNotFoundError(RuntimeError):
    pass


class SupportingItemNotFoundError(RuntimeError):
    pass


class SupportingItemNotConfirmedError(RuntimeError):
    pass


class SupportingDetailValidationError(ValueError):
    pass


def _row_address(row: Any) -> str | None:
    raw = row.raw_data if isinstance(row.raw_data, dict) else {}
    value = raw.get("address")
    return str(value).strip() if value else None


def _food_category(row: FoodBusinessRecord) -> str:
    raw = row.raw_data if isinstance(row.raw_data, dict) else {}
    groups = set(raw.get("supporting_groups") or [])
    if raw.get("supporting_group"):
        groups.add(raw["supporting_group"])
    return "night_business" if "night_economy" in groups else "food"


def _manual_detail(row: Any) -> dict[str, Any]:
    raw = row.raw_data if isinstance(row.raw_data, dict) else {}
    detail = raw.get("manual_detail")
    return dict(detail) if isinstance(detail, dict) else {}


def _supporting_to_public(row: Any, record_type: str) -> dict[str, Any]:
    category = _food_category(row) if record_type == "food" else "entertainment"
    return {
        "id": f"{record_type}:{row.id}",
        "name": row.name,
        "category": category,
        "address": _row_address(row),
        "distance_meters": row.distance_meters,
        "source": row.source,
        "status": row.status,
        "detail_completed": any(
            value is not None and (not isinstance(value, str) or value.strip())
            for value in _manual_detail(row).values()
        ),
        "manual_meta": manual_meta_public(row.raw_data),
    }


def _resolve_supporting_item(db: Session, project_id: str, public_id: str) -> tuple[Any, str]:
    try:
        record_type, raw_id = public_id.split(":", 1)
        record_id = int(raw_id)
    except (TypeError, ValueError):
        raise SupportingItemNotFoundError("Supporting item not found") from None
    model = {"food": FoodBusinessRecord, "entertainment": EntertainmentRecord}.get(record_type)
    if model is None:
        raise SupportingItemNotFoundError("Supporting item not found")
    row = db.scalar(select(model).where(model.project_id == project_id, model.id == record_id))
    if not row:
        raise SupportingItemNotFoundError("Supporting item not found")
    return row, record_type


def list_project_supporting(db: Session, project_id: str) -> dict[str, Any]:
    if not get_project(db, project_id):
        raise SupportingProjectNotFoundError("Project not found")
    food_rows = db.scalars(
        select(FoodBusinessRecord).where(FoodBusinessRecord.project_id == project_id)
        .order_by(FoodBusinessRecord.distance_meters.asc(), FoodBusinessRecord.id.asc())
    ).all()
    entertainment_rows = db.scalars(
        select(EntertainmentRecord).where(EntertainmentRecord.project_id == project_id)
        .order_by(EntertainmentRecord.distance_meters.asc(), EntertainmentRecord.id.asc())
    ).all()
    items = [
        *[_supporting_to_public(row, "food") for row in food_rows],
        *[_supporting_to_public(row, "entertainment") for row in entertainment_rows],
    ]
    stats = {
        category: {"total": 0, "confirmed": 0, "pending_review": 0, "rejected": 0}
        for category in ("food", "entertainment", "night_business")
    }
    for item in items:
        category_stats = stats[item["category"]]
        category_stats["total"] += 1
        category_stats[item["status"]] += 1
    return {
        "items": items,
        "total": len(items),
        "effective_count": sum(category["confirmed"] for category in stats.values()),
        "stats": stats,
    }


def review_project_supporting(
    db: Session,
    project_id: str,
    public_id: str,
    status: str,
) -> dict[str, Any]:
    if not get_project(db, project_id):
        raise SupportingProjectNotFoundError("Project not found")
    row, record_type = _resolve_supporting_item(db, project_id, public_id)
    old_status = row.status
    row.status = status
    row.raw_data = apply_manual_changes(
        db,
        project_id=project_id,
        target_type="supporting",
        target_id=public_id,
        raw_data=row.raw_data,
        old_values={"status": old_status},
        changes={"status": status},
    )
    db.commit()
    db.refresh(row)
    return _supporting_to_public(row, record_type)


def get_project_supporting_detail(db: Session, project_id: str, public_id: str) -> dict[str, Any]:
    if not get_project(db, project_id):
        raise SupportingProjectNotFoundError("Project not found")
    row, record_type = _resolve_supporting_item(db, project_id, public_id)
    return {**_supporting_to_public(row, record_type), "manual_detail": _manual_detail(row)}


def update_project_supporting_detail(
    db: Session,
    project_id: str,
    public_id: str,
    changes: dict[str, Any],
) -> dict[str, Any]:
    if not get_project(db, project_id):
        raise SupportingProjectNotFoundError("Project not found")
    row, record_type = _resolve_supporting_item(db, project_id, public_id)
    if row.status != "confirmed":
        raise SupportingItemNotConfirmedError("Only confirmed supporting items can be updated")

    unknown_value = changes.pop("unknown_fields", None)
    unknown_fields = list(unknown_value or []) if unknown_value is not None else None
    category = _food_category(row) if record_type == "food" else "entertainment"
    common_fields = {"business_hours", "opening_date", "remark", "night_operation"}
    category_fields = {
        "food": {"food_type"},
        "entertainment": {"entertainment_type"},
        "night_business": {"is_24_hours", "night_flow_remark"},
    }
    allowed_fields = common_fields | category_fields[category]
    unsupported = {
        field_name
        for field_name, value in changes.items()
        if value is not None and field_name not in allowed_fields
    }
    if unsupported:
        raise SupportingDetailValidationError(
            f"当前分类不支持字段: {', '.join(sorted(unsupported))}"
        )

    raw = dict(row.raw_data or {})
    manual_detail = _manual_detail(row)
    old_values: dict[str, Any] = {}
    audit_changes: dict[str, Any] = {}
    for field_name in allowed_fields:
        if field_name in changes:
            old_values[field_name] = manual_detail.get(field_name)
            manual_detail[field_name] = changes[field_name]
            audit_changes[field_name] = changes[field_name]
    raw["manual_detail"] = manual_detail
    row.raw_data = apply_manual_changes(
        db,
        project_id=project_id,
        target_type="supporting",
        target_id=public_id,
        raw_data=raw,
        old_values=old_values,
        changes=audit_changes,
        unknown_fields=unknown_fields,
    )
    db.commit()
    db.refresh(row)
    return {**_supporting_to_public(row, record_type), "manual_detail": _manual_detail(row)}


def _address(item: Any) -> str | None:
    raw = item.raw_data if isinstance(item.raw_data, dict) else {}
    value = raw.get("address")
    return str(value).strip() if value else None


def _existing_record(db: Session, model: Any, project_id: str, item: Any):
    rows = db.scalars(
        select(model).where(
            model.project_id == project_id,
            model.source == "amap",
            model.name == item.name,
        )
    ).all()
    target_address = _address(item)
    for row in rows:
        raw = row.raw_data if isinstance(row.raw_data, dict) else {}
        existing_address = str(raw.get("address")).strip() if raw.get("address") else None
        if existing_address == target_address:
            return row
    return None


def _save_item(db: Session, model: Any, project_id: str, item: Any) -> bool:
    existing = _existing_record(db, model, project_id, item)
    payload = item.model_dump(mode="python")
    columns = model.__table__.columns.keys()
    payload = {key: value for key, value in payload.items() if key in columns}
    payload["project_id"] = project_id
    payload["timestamp"] = datetime.now(timezone.utc)
    if existing:
        incoming_raw = payload.pop("raw_data", {}) or {}
        existing_raw = dict(existing.raw_data or {})
        groups = set(existing_raw.get("supporting_groups") or [])
        if existing_raw.get("supporting_group"):
            groups.add(existing_raw["supporting_group"])
        if incoming_raw.get("supporting_group"):
            groups.add(incoming_raw["supporting_group"])
        existing_raw.update(incoming_raw)
        existing_raw["supporting_groups"] = sorted(groups)
        existing.raw_data = existing_raw
        for key, value in payload.items():
            if key not in {"id", "project_id", "status"} and value is not None:
                setattr(existing, key, value)
        return False
    raw = dict(payload.get("raw_data") or {})
    if raw.get("supporting_group"):
        raw["supporting_groups"] = [raw["supporting_group"]]
    payload["raw_data"] = raw
    db.add(model(**payload))
    return True


def _night_activity_level(count: int) -> str:
    if count >= 8:
        return "high"
    if count >= 3:
        return "medium"
    if count > 0:
        return "low"
    return "none"


async def collect_project_supporting(
    db: Session,
    project_id: str,
    *,
    registry: DataSourceRegistry | None = None,
) -> dict[str, Any]:
    project: SiteProjectRecord | None = get_project(db, project_id)
    if not project:
        raise SupportingProjectNotFoundError("Project not found")

    provider = (registry or build_default_registry()).get("amap_supporting")
    request = DataSourceRequest(
        project_id=project.project_id,
        city=project.city,
        longitude=project.longitude,
        latitude=project.latitude,
        radius_meters=project.radius_meters,
    )
    food_result = await provider.get_food(request)
    entertainment_result = await provider.get_entertainment(request)
    night_result = await provider.get_night_economy(request)
    results = (food_result, entertainment_result, night_result)
    warnings = [warning for result in results for warning in result.warnings]

    if all(result.status == ProviderCallStatus.failed for result in results):
        analysis = {
            "food_count": 0,
            "entertainment_count": 0,
            "night_business_count": 0,
            "night_activity_level": "none",
        }
        return {
            "success": False,
            "project_id": project.project_id,
            "provider": provider.name,
            **analysis,
            "created_count": 0,
            "updated_count": 0,
            "supporting_analysis": analysis,
            "warnings": warnings,
            "message": warnings[0] if warnings else "周边配套采集失败",
        }

    created_count = 0
    updated_count = 0
    for item in [*food_result.items, *night_result.items]:
        if _save_item(db, FoodBusinessRecord, project.project_id, item):
            created_count += 1
        else:
            updated_count += 1
    for item in entertainment_result.items:
        if _save_item(db, EntertainmentRecord, project.project_id, item):
            created_count += 1
        else:
            updated_count += 1
    db.commit()

    analysis = {
        "food_count": len(food_result.items),
        "entertainment_count": len(entertainment_result.items),
        "night_business_count": len(night_result.items),
        "night_activity_level": _night_activity_level(len(night_result.items)),
    }
    return {
        "success": True,
        "project_id": project.project_id,
        "provider": provider.name,
        **analysis,
        "created_count": created_count,
        "updated_count": updated_count,
        "supporting_analysis": analysis,
        "warnings": warnings,
        "message": "未发现周边配套数据" if not any(analysis[key] for key in ("food_count", "entertainment_count", "night_business_count")) else "周边配套采集完成",
    }
