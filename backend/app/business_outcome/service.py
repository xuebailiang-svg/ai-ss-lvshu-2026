from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import BusinessOutcomeRecord, MemoryItemRecord
from app.projects.service import get_project


class BusinessOutcomeNotFoundError(RuntimeError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _public(row: BusinessOutcomeRecord) -> dict[str, Any]:
    return {column.name: getattr(row, column.name) for column in row.__table__.columns}


def get_outcome(db: Session, project_id: str) -> dict[str, Any] | None:
    if not get_project(db, project_id):
        raise BusinessOutcomeNotFoundError("Project not found")
    row = db.scalar(select(BusinessOutcomeRecord).where(BusinessOutcomeRecord.project_id == project_id))
    return _public(row) if row else None


def upsert_outcome(db: Session, project_id: str, values: dict[str, Any]) -> dict[str, Any]:
    if not get_project(db, project_id):
        raise BusinessOutcomeNotFoundError("Project not found")
    row = db.scalar(select(BusinessOutcomeRecord).where(BusinessOutcomeRecord.project_id == project_id))
    if not row:
        row = BusinessOutcomeRecord(project_id=project_id, created_at=_now(), updated_at=_now())
        db.add(row)
    for field, value in values.items():
        setattr(row, field, value)
    row.status = "pending_review"
    row.reviewed_at = None
    row.updated_at = _now()
    db.commit()
    db.refresh(row)
    return _public(row)


def review_outcome(db: Session, project_id: str, status: str) -> dict[str, Any]:
    project = get_project(db, project_id)
    row = db.scalar(select(BusinessOutcomeRecord).where(BusinessOutcomeRecord.project_id == project_id))
    if not project or not row:
        raise BusinessOutcomeNotFoundError("Business outcome not found")
    row.status = status
    row.reviewed_at = _now() if status != "pending_review" else None
    row.updated_at = _now()
    if status == "confirmed":
        content = json.dumps({
            "actual_monthly_rent": row.actual_monthly_rent,
            "actual_area_sqm": row.actual_area_sqm,
            "actual_machine_count": row.actual_machine_count,
            "opening_date": row.opening_date.isoformat() if row.opening_date else None,
            "actual_investment": row.actual_investment,
            "occupancy_rate": row.occupancy_rate,
            "result_status": row.result_status,
            "success_reasons": row.success_reasons,
            "failure_reasons": row.failure_reasons,
            "notes": row.notes,
        }, ensure_ascii=False)
        memory = db.scalar(select(MemoryItemRecord).where(
            MemoryItemRecord.project_id == project_id,
            MemoryItemRecord.memory_type == "case_feedback",
            MemoryItemRecord.source == "business_outcome",
        ))
        if not memory:
            memory = MemoryItemRecord(
                scope="project", memory_type="case_feedback", project_id=project_id,
                title=f"{project.project_name or project.address}真实经营结果", source="business_outcome",
                created_at=_now(),
            )
            db.add(memory)
        memory.content = content
        memory.tags = [project.city, project.district, project.business_type, "真实经营反馈"]
        memory.confidence = .95
        memory.status = "confirmed"
        memory.raw_data = {"business_outcome_id": row.id}
        memory.updated_at = _now()
    else:
        memory = db.scalar(select(MemoryItemRecord).where(
            MemoryItemRecord.project_id == project_id,
            MemoryItemRecord.memory_type == "case_feedback",
            MemoryItemRecord.source == "business_outcome",
        ))
        if memory:
            memory.status = "rejected" if status == "rejected" else "pending_review"
            memory.updated_at = _now()
    db.commit()
    db.refresh(row)
    return _public(row)
