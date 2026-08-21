from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.manual_input.validators import validate_manual_payload
from app.models import (
    ManualInputRecord,
    PopulationDataRecord,
    RentDataRecord,
    SiteProjectRecord,
    SupplementRecord,
    UnifiedCompetitorRecord,
)
from app.projects.service import get_project, latest_for_project, row_to_dict
from app.manual_input.audit import apply_manual_changes


class ProjectNotFoundError(RuntimeError):
    pass


class ManualInputValidationError(ValueError):
    pass


def _require_project(db: Session, project_id: str) -> SiteProjectRecord:
    project = get_project(db, project_id)
    if not project:
        raise ProjectNotFoundError("Project not found")
    return project


def _json_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _record_history(
    db: Session,
    *,
    project_id: str,
    target_type: str,
    target_id: str | None,
    field_name: str,
    old_value: Any,
    new_value: Any,
    confidence: float = 0.8,
) -> None:
    db.add(
        ManualInputRecord(
            project_id=project_id,
            target_type=target_type,
            target_id=str(target_id) if target_id is not None else None,
            field_name=field_name,
            old_value=_json_value(old_value),
            new_value=_json_value(new_value),
            source="manual",
            confidence=confidence,
            created_at=datetime.now(timezone.utc),
        )
    )


def missing_data(db: Session, project_id: str) -> dict[str, Any]:
    _require_project(db, project_id)
    competitors = db.scalars(select(UnifiedCompetitorRecord).where(UnifiedCompetitorRecord.project_id == project_id)).all()
    rent = latest_for_project(db, RentDataRecord, project_id)
    missing: list[dict[str, str]] = []

    if not competitors:
        missing.append({"type": "competitor", "field": "name", "description": "缺少竞品基础数据"})
    else:
        if not any(row.hour_price is not None or row.member_price is not None for row in competitors):
            missing.append({"type": "competitor", "field": "hour_price", "description": "缺少竞品价格"})
        if not any(row.occupancy_rate is not None for row in competitors):
            missing.append({"type": "competitor", "field": "occupancy_rate", "description": "缺少竞品上座率"})
        if not any(row.machine_count is not None or row.cpu or row.gpu or row.monitor for row in competitors):
            missing.append({"type": "competitor", "field": "machine_count", "description": "缺少竞品机器数量或配置"})
        if not any(row.monthly_sales is not None or row.annual_sales is not None for row in competitors):
            missing.append({"type": "competitor", "field": "monthly_sales", "description": "缺少竞品月销售或年销售"})
    if not rent or not rent.get("monthly_rent"):
        missing.append({"type": "rent", "field": "monthly_rent", "description": "缺少真实租金"})
    return {"project_id": project_id, "missing": missing}


def list_manual_inputs(db: Session, project_id: str) -> list[dict[str, Any]]:
    _require_project(db, project_id)
    rows = db.scalars(
        select(ManualInputRecord)
        .where(ManualInputRecord.project_id == project_id)
        .order_by(ManualInputRecord.created_at.desc(), ManualInputRecord.id.desc())
    ).all()
    return [row_to_dict(row) for row in rows]


def save_manual_input(
    db: Session,
    project_id: str,
    data_type: str,
    target_id: str | None,
    data: dict[str, Any],
) -> dict[str, Any]:
    _require_project(db, project_id)
    try:
        payload = validate_manual_payload(data_type, data)
    except ValueError as exc:
        raise ManualInputValidationError(str(exc)) from exc

    if data_type == "competitor":
        updated = _save_competitor(db, project_id, target_id, payload)
        message = "竞品数据补充成功"
    elif data_type == "rent":
        updated = _save_rent(db, project_id, payload)
        message = "租金数据补充成功"
    elif data_type == "population":
        updated = _save_population(db, project_id, payload)
        message = "人口数据补充成功"
    elif data_type == "supplement":
        updated = _save_supplement(db, project_id, target_id, payload)
        message = "通用备注补充成功"
    elif data_type == "property":
        updated = _save_property(db, project_id, payload)
        message = "候选物业信息保存成功"
    else:
        raise ManualInputValidationError(f"unsupported manual input type: {data_type}")

    db.commit()
    return {"success": True, "message": message, "updated": updated}


def _save_competitor(db: Session, project_id: str, target_id: str | None, payload: dict[str, Any]) -> dict[str, Any]:
    competitor = None
    if target_id and str(target_id).isdigit():
        competitor = db.scalar(
            select(UnifiedCompetitorRecord).where(
                UnifiedCompetitorRecord.project_id == project_id,
                UnifiedCompetitorRecord.id == int(target_id),
            )
        )
    created = competitor is None
    if created:
        competitor = UnifiedCompetitorRecord(
            project_id=project_id,
            name=str(payload.get("name") or "人工补充竞品"),
            source="manual",
            confidence=0.8,
            status="confirmed",
            raw_data={},
        )
        db.add(competitor)
        db.flush()

    unknown_value = payload.pop("unknown_fields", None)
    unknown_fields = list(unknown_value or []) if unknown_value is not None else None
    raw_data = dict(competitor.raw_data or {})
    existing_manual_detail = raw_data.get("manual_detail")
    manual_detail = dict(existing_manual_detail) if isinstance(existing_manual_detail, dict) else {}
    table_fields = set(UnifiedCompetitorRecord.__table__.columns.keys())
    old_values: dict[str, Any] = {}
    audit_changes: dict[str, Any] = {}
    for field, value in payload.items():
        old_value = getattr(competitor, field, None) if field in table_fields else manual_detail.get(field)
        old_values[field] = old_value
        if field in table_fields:
            setattr(competitor, field, value)
        else:
            manual_detail[field] = value
        audit_changes[field] = value
    raw_data["manual_detail"] = manual_detail
    raw_data = apply_manual_changes(
        db,
        project_id=project_id,
        target_type="competitor",
        target_id=str(competitor.id),
        raw_data=raw_data,
        old_values=old_values,
        changes=audit_changes,
        unknown_fields=unknown_fields,
    )
    if created:
        competitor.source = "manual"
    competitor.confidence = max(float(competitor.confidence or 0), 0.8)
    competitor.status = "confirmed"
    competitor.timestamp = datetime.now(timezone.utc)
    competitor.raw_data = raw_data
    return row_to_dict(competitor)


def _save_rent(db: Session, project_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    rent = db.scalar(select(RentDataRecord).where(RentDataRecord.project_id == project_id).order_by(RentDataRecord.timestamp.desc(), RentDataRecord.id.desc()))
    if rent is None:
        rent = RentDataRecord(project_id=project_id, source="manual", confidence=0.8, status="confirmed", raw_data={})
        db.add(rent)
        db.flush()

    raw_data = dict(rent.raw_data or {})
    raw_data.update({"manual_input": payload})
    table_fields = set(RentDataRecord.__table__.columns.keys())
    for field, value in payload.items():
        old_value = getattr(rent, field, None) if field in table_fields else raw_data.get(field)
        if field in table_fields:
            setattr(rent, field, value)
        else:
            raw_data[field] = value
        _record_history(db, project_id=project_id, target_type="rent", target_id=str(rent.id), field_name=field, old_value=old_value, new_value=value)
    rent.source = "manual"
    rent.confidence = max(float(rent.confidence or 0), 0.8)
    rent.status = "confirmed"
    rent.timestamp = datetime.now(timezone.utc)
    rent.raw_data = raw_data
    return row_to_dict(rent)


def _save_population(db: Session, project_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    population = db.scalar(
        select(PopulationDataRecord)
        .where(PopulationDataRecord.project_id == project_id)
        .order_by(PopulationDataRecord.timestamp.desc(), PopulationDataRecord.id.desc())
    )
    if population is None:
        population = PopulationDataRecord(project_id=project_id, source="manual", confidence=0.8, status="confirmed", raw_data={})
        db.add(population)
        db.flush()

    raw_data = dict(population.raw_data or {})
    raw_data.update({"manual_input": payload})
    table_fields = set(PopulationDataRecord.__table__.columns.keys())
    for field, value in payload.items():
        old_value = getattr(population, field, None) if field in table_fields else raw_data.get(field)
        if field in table_fields:
            setattr(population, field, value)
        else:
            raw_data[field] = value
        _record_history(db, project_id=project_id, target_type="population", target_id=str(population.id), field_name=field, old_value=old_value, new_value=value)
    population.source = "manual"
    population.confidence = max(float(population.confidence or 0), 0.8)
    population.status = "confirmed"
    population.timestamp = datetime.now(timezone.utc)
    population.raw_data = raw_data
    return row_to_dict(population)


def _save_supplement(db: Session, project_id: str, target_id: str | None, payload: dict[str, Any]) -> dict[str, Any]:
    row = SupplementRecord(
        project_id=project_id,
        target_type=str(payload.get("target_type") or "project"),
        target_id=str(payload.get("target_id") or target_id) if (payload.get("target_id") or target_id) is not None else None,
        field_name=str(payload.get("field_name") or "remark"),
        value=payload.get("value", payload.get("remark")),
        source="manual",
        confidence=0.8,
        status="confirmed",
        raw_data=payload,
        timestamp=datetime.now(timezone.utc),
        created_time=datetime.now(timezone.utc),
    )
    db.add(row)
    db.flush()
    _record_history(
        db,
        project_id=project_id,
        target_type=row.target_type,
        target_id=row.target_id,
        field_name=row.field_name,
        old_value=None,
        new_value=row.value,
    )
    return row_to_dict(row)


def _save_property(db: Session, project_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    row = db.scalar(
        select(SupplementRecord).where(
            SupplementRecord.project_id == project_id,
            SupplementRecord.target_type == "candidate_property",
            SupplementRecord.field_name == "manual_detail",
        ).order_by(SupplementRecord.id.desc())
    )
    now = datetime.now(timezone.utc)
    if row is None:
        row = SupplementRecord(
            project_id=project_id,
            target_type="candidate_property",
            target_id="primary",
            field_name="manual_detail",
            value={},
            source="manual",
            confidence=0.8,
            status="confirmed",
            raw_data={},
            timestamp=now,
            created_time=now,
        )
        db.add(row)
        db.flush()
    old_value = dict(row.value) if isinstance(row.value, dict) else {}
    unknown_value = payload.pop("unknown_fields", None)
    unknown_fields = list(unknown_value or []) if unknown_value is not None else None
    row.value = {**old_value, **payload}
    row.timestamp = now
    row.raw_data = apply_manual_changes(
        db,
        project_id=project_id,
        target_type="candidate_property",
        target_id="primary",
        raw_data=row.raw_data,
        old_values=old_value,
        changes=payload,
        unknown_fields=unknown_fields,
    )
    return row_to_dict(row)
