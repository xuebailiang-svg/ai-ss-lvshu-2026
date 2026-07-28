from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_HEALTH_FILE = "/var/lib/esports-site-selection/crawler/worker-health.json"


def health_file_path() -> Path:
    return Path(os.getenv("CRAWLER_HEALTH_FILE", DEFAULT_HEALTH_FILE))


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def read_worker_health(*, stale_after_seconds: int = 90) -> dict[str, Any]:
    path = health_file_path()
    if not path.is_file():
        return {
            "installed": False,
            "reachable": False,
            "status": "not_installed",
            "message": "独立爬虫 Worker 尚未安装或尚未生成健康状态",
            "health_file": str(path),
        }
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "installed": True,
            "reachable": False,
            "status": "failed",
            "message": f"无法读取爬虫 Worker 健康状态：{exc}",
            "health_file": str(path),
        }

    checked_at = _parse_datetime(payload.get("checked_at"))
    age_seconds = max(0, int((utc_now() - checked_at).total_seconds())) if checked_at else None
    stale = age_seconds is None or age_seconds > stale_after_seconds
    ready = payload.get("status") == "ok" and bool(payload.get("browser_ready")) and not stale
    result = {
        **payload,
        "installed": True,
        "reachable": ready,
        "status": "ok" if ready else ("stale" if stale else payload.get("status", "failed")),
        "age_seconds": age_seconds,
        "health_file": str(path),
    }
    if stale:
        result["message"] = "爬虫 Worker 状态已过期，请检查独立服务"
    return result


def write_worker_health(payload: dict[str, Any]) -> None:
    path = health_file_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    content = {**payload, "checked_at": utc_now().isoformat()}
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(content, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)
