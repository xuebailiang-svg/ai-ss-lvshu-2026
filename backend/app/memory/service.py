from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import MemoryItemRecord
from app.memory.schemas import MemoryItemCreate, MemoryItemUpdate


VALID_STATUSES = {"pending_review", "confirmed", "disabled"}


def memory_to_dict(row: MemoryItemRecord) -> dict:
    return {
        "id": row.id,
        "scope": row.scope,
        "memory_type": row.memory_type,
        "title": row.title,
        "content": row.content,
        "tags": row.tags or [],
        "source": row.source,
        "confidence": row.confidence,
        "status": row.status,
        "project_id": row.project_id,
        "user_id": row.user_id,
        "raw_data": row.raw_data or {},
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def list_memory_items(
    db: Session,
    *,
    project_id: str | None = None,
    scope: str | None = None,
    memory_type: str | None = None,
    status: str | None = None,
) -> list[MemoryItemRecord]:
    stmt = select(MemoryItemRecord)
    if project_id:
        stmt = stmt.where(or_(MemoryItemRecord.project_id == project_id, MemoryItemRecord.scope == "global"))
    if scope:
        stmt = stmt.where(MemoryItemRecord.scope == scope)
    if memory_type:
        stmt = stmt.where(MemoryItemRecord.memory_type == memory_type)
    if status:
        stmt = stmt.where(MemoryItemRecord.status == status)
    return list(db.scalars(stmt.order_by(MemoryItemRecord.updated_at.desc(), MemoryItemRecord.id.desc())).all())


def create_memory_item(db: Session, body: MemoryItemCreate) -> MemoryItemRecord:
    now = datetime.now(timezone.utc)
    row = MemoryItemRecord(**body.model_dump(), created_at=now, updated_at=now)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get_memory_item(db: Session, memory_id: int) -> MemoryItemRecord | None:
    return db.get(MemoryItemRecord, memory_id)


def update_memory_item(db: Session, row: MemoryItemRecord, body: MemoryItemUpdate) -> MemoryItemRecord:
    values = body.model_dump(exclude_unset=True)
    for key, value in values.items():
        setattr(row, key, value)
    row.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    return row


def review_memory_item(db: Session, row: MemoryItemRecord, status: str) -> MemoryItemRecord:
    if status not in VALID_STATUSES:
        raise ValueError("Invalid memory status")
    row.status = status
    row.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    return row


def relevant_memory_context(
    db: Session,
    project_id: str,
    *,
    tags: Iterable[str] | None = None,
    limit: int = 30,
) -> list[dict]:
    rows = list_memory_items(db, project_id=project_id, status="confirmed")
    tag_set = {tag for tag in (tags or []) if tag}
    if tag_set:
        rows = [row for row in rows if tag_set.intersection(set(row.tags or []))]
    return [memory_to_dict(row) for row in rows[:limit]]
