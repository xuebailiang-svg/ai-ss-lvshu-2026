from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def blank_to_none(value: Any) -> Any:
    if isinstance(value, str) and not value.strip():
        return None
    return value


def to_float(value: Any) -> float | None:
    value = blank_to_none(value)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def to_int(value: Any) -> int | None:
    value = blank_to_none(value)
    if value is None:
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def to_bool(value: Any) -> bool | None:
    value = blank_to_none(value)
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "是", "有", "营业", "open"}:
        return True
    if text in {"0", "false", "no", "n", "否", "无", "不营业", "closed"}:
        return False
    return None


def parse_location(value: Any) -> tuple[float | None, float | None]:
    if not value:
        return None, None
    if isinstance(value, (list, tuple)) and len(value) >= 2:
        return to_float(value[0]), to_float(value[1])
    text = str(value).strip()
    if "," not in text:
        return None, None
    left, right = text.split(",", 1)
    return to_float(left), to_float(right)
