from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models import ManualInputRecord


def manual_meta(raw_data: Any) -> dict[str, Any]:
    raw = raw_data if isinstance(raw_data, dict) else {}
    value = raw.get("_manual_meta")
    return dict(value) if isinstance(value, dict) else {}


def apply_manual_changes(
    db: Session,
    *,
    project_id: str,
    target_type: str,
    target_id: str | int,
    raw_data: Any,
    old_values: dict[str, Any],
    changes: dict[str, Any],
    unknown_fields: list[str] | None = None,
) -> dict[str, Any]:
    raw = dict(raw_data) if isinstance(raw_data, dict) else {}
    meta = manual_meta(raw)
    field_sources = dict(meta.get("field_sources") or {})
    unknown = set(meta.get("unknown_fields") or [])
    history = list(meta.get("history") or [])
    now = datetime.now(timezone.utc)

    for field_name, new_value in changes.items():
        old_value = old_values.get(field_name)
        if old_value == new_value:
            continue
        field_sources[field_name] = "manual"
        unknown.discard(field_name)
        history.append(
            {
                "field": field_name,
                "old_value": old_value,
                "new_value": new_value,
                "source": "manual",
                "changed_at": now.isoformat(),
            }
        )
        db.add(
            ManualInputRecord(
                project_id=project_id,
                target_type=target_type,
                target_id=str(target_id),
                field_name=field_name,
                old_value=old_value,
                new_value=new_value,
                source="manual",
                confidence=0.8,
                created_at=now,
            )
        )

    if unknown_fields is not None:
        desired_unknown = set(unknown_fields)
        for field_name in sorted(unknown - desired_unknown):
            unknown.discard(field_name)
            if field_sources.get(field_name) == "manual_unknown":
                field_sources.pop(field_name, None)
            history.append(
                {
                    "field": field_name,
                    "old_value": "unknown",
                    "new_value": None,
                    "source": "manual_unknown_clear",
                    "changed_at": now.isoformat(),
                }
            )
            db.add(
                ManualInputRecord(
                    project_id=project_id,
                    target_type=target_type,
                    target_id=str(target_id),
                    field_name=field_name,
                    old_value="unknown",
                    new_value=None,
                    source="manual",
                    confidence=0.8,
                    created_at=now,
                )
            )
        for field_name in sorted(desired_unknown - unknown):
            unknown.add(field_name)
            field_sources[field_name] = "manual_unknown"
            history.append(
                {
                    "field": field_name,
                    "old_value": old_values.get(field_name),
                    "new_value": "unknown",
                    "source": "manual_unknown",
                    "changed_at": now.isoformat(),
                }
            )
            db.add(
                ManualInputRecord(
                    project_id=project_id,
                    target_type=target_type,
                    target_id=str(target_id),
                    field_name=field_name,
                    old_value=old_values.get(field_name),
                    new_value="unknown",
                    source="manual",
                    confidence=0.8,
                    created_at=now,
                )
            )

    raw["_manual_meta"] = {
        "field_sources": field_sources,
        "unknown_fields": sorted(unknown),
        "verified_at": now.isoformat(),
        "history": history[-100:],
    }
    return raw


def manual_meta_public(raw_data: Any) -> dict[str, Any]:
    meta = manual_meta(raw_data)
    return {
        "field_sources": dict(meta.get("field_sources") or {}),
        "unknown_fields": list(meta.get("unknown_fields") or []),
        "verified_at": meta.get("verified_at"),
        "history_count": len(meta.get("history") or []),
    }
