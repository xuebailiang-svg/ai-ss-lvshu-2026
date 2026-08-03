from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.data_source.crawler.evidence import freshness_for_detail, source_quality_for_url
from app.models import (
    CrawlTaskRecord,
    CrawlerFieldSuggestionRecord,
    EntertainmentRecord,
    FoodBusinessRecord,
    RentDataRecord,
    UnifiedCompetitorRecord,
)
from app.projects.service import get_project


class CrawlerSuggestionNotFoundError(RuntimeError):
    pass


DIRECT_FIELDS = {
    "competitor": {"area_sqm", "machine_count", "hour_price", "member_price", "occupancy_rate", "opening_date"},
    "food": {"business_hours", "night_business", "rating", "opening_date"},
    "entertainment": {"business_hours", "night_business", "opening_date"},
    "rent": {"monthly_rent", "area_sqm", "rent_per_sqm"},
}
FIELD_ALIASES = {"night_operation": "night_business", "rent_per_sqm": "rent_per_sqm"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _record_type(payload: dict[str, Any]) -> str:
    if payload.get("task_type") == "supporting":
        return str(payload.get("record_type") or "food")
    return str(payload.get("task_type") or "")


def _get_record(db: Session, project_id: str, record_type: str, record_id: int | None) -> Any | None:
    if record_id is None:
        return None
    model = {
        "competitor": UnifiedCompetitorRecord,
        "food": FoodBusinessRecord,
        "entertainment": EntertainmentRecord,
        "rent": RentDataRecord,
    }.get(record_type)
    if not model:
        return None
    return db.scalar(select(model).where(model.project_id == project_id, model.id == record_id))


def _current_value(row: Any | None, record_type: str, field_name: str) -> Any:
    if row is None:
        return None
    field = FIELD_ALIASES.get(field_name, field_name)
    if field in DIRECT_FIELDS.get(record_type, set()):
        return getattr(row, field, None)
    raw = row.raw_data if isinstance(row.raw_data, dict) else {}
    manual = raw.get("manual_detail") if isinstance(raw.get("manual_detail"), dict) else {}
    return manual.get(field_name)


def persist_task_suggestions(
    db: Session,
    task: CrawlTaskRecord,
    payload: dict[str, Any],
    detail: dict[str, Any],
    evidence: list[dict[str, Any]],
    record: Any | None,
) -> int:
    record_type = _record_type(payload)
    record_id = getattr(record, "id", None) or payload.get("record_id")
    created = 0
    for item in evidence:
        field = str(item.get("field") or "")
        source_url = str(item.get("source_url") or detail.get("source_url") or task.target_url or "")
        if not field or not source_url:
            continue
        existing = db.scalar(
            select(CrawlerFieldSuggestionRecord).where(
                CrawlerFieldSuggestionRecord.task_id == task.id,
                CrawlerFieldSuggestionRecord.record_type == record_type,
                CrawlerFieldSuggestionRecord.record_id == record_id,
                CrawlerFieldSuggestionRecord.field_name == field,
                CrawlerFieldSuggestionRecord.source_url == source_url,
            )
        )
        current = _current_value(record, record_type, field)
        conflict = "existing_value" if current not in (None, "") and current != item.get("value") else "none"
        values = {
            "project_id": task.project_id,
            "task_id": task.id,
            "record_type": record_type,
            "record_id": record_id,
            "field_name": field,
            "suggested_value": item.get("value"),
            "source_url": source_url,
            "source_domain": item.get("source_domain") or (urlparse(source_url).netloc or "").lower(),
            "evidence_excerpt": item.get("excerpt"),
            "extraction_method": item.get("method") or "rule_extract",
            "confidence": float(item.get("confidence") or .6),
            "source_quality": item.get("source_quality") or source_quality_for_url(source_url),
            "freshness_status": item.get("freshness_status") or freshness_for_detail(detail),
            "conflict_status": conflict,
        }
        if existing:
            for key, value in values.items():
                setattr(existing, key, value)
        else:
            db.add(CrawlerFieldSuggestionRecord(**values, status="pending_review", created_at=_now(), updated_at=_now()))
            created += 1
    return created


def _public(row: CrawlerFieldSuggestionRecord) -> dict[str, Any]:
    return {
        "id": row.id,
        "project_id": row.project_id,
        "task_id": row.task_id,
        "record_type": row.record_type,
        "record_id": row.record_id,
        "field_name": row.field_name,
        "suggested_value": row.suggested_value,
        "reviewed_value": row.reviewed_value,
        "source_url": row.source_url,
        "source_domain": row.source_domain,
        "evidence_excerpt": row.evidence_excerpt,
        "extraction_method": row.extraction_method,
        "confidence": row.confidence,
        "source_quality": row.source_quality,
        "freshness_status": row.freshness_status,
        "conflict_status": row.conflict_status,
        "status": row.status,
        "review_remark": row.review_remark,
        "reviewed_at": row.reviewed_at,
        "created_at": row.created_at,
    }


def list_suggestions(db: Session, project_id: str, status: str | None = None) -> dict[str, Any]:
    if not get_project(db, project_id):
        raise CrawlerSuggestionNotFoundError("Project not found")
    query = select(CrawlerFieldSuggestionRecord).where(CrawlerFieldSuggestionRecord.project_id == project_id)
    if status:
        query = query.where(CrawlerFieldSuggestionRecord.status == status)
    rows = db.scalars(query.order_by(CrawlerFieldSuggestionRecord.created_at.desc(), CrawlerFieldSuggestionRecord.id.desc())).all()
    return {"items": [_public(row) for row in rows], "total": len(rows)}


def _apply_value(row: Any, record_type: str, field_name: str, value: Any) -> None:
    field = FIELD_ALIASES.get(field_name, field_name)
    if field in DIRECT_FIELDS.get(record_type, set()):
        if field == "machine_count" and value is not None:
            value = int(value)
        setattr(row, field, value)
        return
    raw = dict(row.raw_data or {})
    manual = dict(raw.get("manual_detail") or {})
    manual[field_name] = value
    raw["manual_detail"] = manual
    row.raw_data = raw


def review_suggestion(
    db: Session,
    project_id: str,
    suggestion_id: int,
    *,
    action: str,
    final_value: Any = None,
    remark: str | None = None,
) -> dict[str, Any]:
    row = db.scalar(select(CrawlerFieldSuggestionRecord).where(
        CrawlerFieldSuggestionRecord.project_id == project_id,
        CrawlerFieldSuggestionRecord.id == suggestion_id,
    ))
    if not row:
        raise CrawlerSuggestionNotFoundError("Crawler suggestion not found")
    if action == "accepted":
        record = _get_record(db, project_id, row.record_type, row.record_id)
        if not record:
            raise CrawlerSuggestionNotFoundError("Target record not found")
        value = row.suggested_value if final_value is None else final_value
        _apply_value(record, row.record_type, row.field_name, value)
        row.reviewed_value = value
    row.status = action
    row.review_remark = remark
    row.reviewed_at = _now()
    row.updated_at = _now()
    db.commit()
    db.refresh(row)
    return _public(row)


def confirmed_evidence_summary(db: Session, project_id: str) -> list[dict[str, Any]]:
    rows = db.scalars(select(CrawlerFieldSuggestionRecord).where(
        CrawlerFieldSuggestionRecord.project_id == project_id,
        CrawlerFieldSuggestionRecord.status == "accepted",
    ).order_by(CrawlerFieldSuggestionRecord.id.asc())).all()
    return [
        {
            "record_type": row.record_type,
            "record_id": row.record_id,
            "field": row.field_name,
            "value": row.reviewed_value if row.reviewed_value is not None else row.suggested_value,
            "source_domain": row.source_domain,
            "source_url": row.source_url,
            "evidence": row.evidence_excerpt,
            "confidence": row.confidence,
            "source_quality": row.source_quality,
            "freshness_status": row.freshness_status,
            "review_status": "accepted",
        }
        for row in rows
    ]


def retry_task(db: Session, project_id: str, task_id: int) -> CrawlTaskRecord:
    source = db.scalar(select(CrawlTaskRecord).where(CrawlTaskRecord.project_id == project_id, CrawlTaskRecord.id == task_id))
    if not source:
        raise CrawlerSuggestionNotFoundError("Crawl task not found")
    payload = dict(source.input_snapshot or {})
    payload["retry_of_task_id"] = source.id
    task = CrawlTaskRecord(
        project_id=project_id,
        task_type=source.task_type,
        target_name=source.target_name,
        target_address=source.target_address,
        target_url=source.target_url,
        provider=source.provider,
        status="pending",
        source_domain=source.source_domain,
        input_snapshot=payload,
        result_snapshot={},
        created_at=_now(),
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task
