from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.config import get_settings


class SiteFeedbackStore:
    """File-backed feedback store for the first learning-loop phase.

    It intentionally avoids database migrations. The file can later be replaced
    by a database table without changing the Agent/tool contract.
    """

    _lock = threading.RLock()

    def __init__(self, path: str | None = None):
        self.path = Path(path or get_settings().site_feedback_store_path)
        if not self.path.is_absolute():
            self.path = Path.cwd() / self.path

    def list_events(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return []
        if isinstance(data, dict) and isinstance(data.get("events"), list):
            return data["events"]
        if isinstance(data, list):
            # Backward compatibility for the pre-event-log JSON format.
            return [
                {
                    "event_type": "feedback_initialized",
                    "task_id": row.get("task_id"),
                    "payload": row,
                    "timestamp": row.get("updated_at") or row.get("created_at") or self._now(),
                }
                for row in data
            ]
        return []

    def list_records(self) -> list[dict[str, Any]]:
        records: dict[str, dict[str, Any]] = {}
        for event in self.list_events():
            task_id = event.get("task_id")
            if not task_id:
                continue
            payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
            current = records.setdefault(task_id, {"task_id": task_id})
            if event.get("event_type") in {"agent_run_completed", "feedback_initialized"}:
                current.update(payload)
            elif event.get("event_type") == "feedback_updated":
                current.update(
                    {
                        "actual_business_result": payload.get("actual_business_result", "unknown"),
                        "user_feedback": payload.get("user_feedback", ""),
                        "monthly_revenue_range": payload.get("monthly_revenue_range"),
                        "updated_at": event.get("timestamp"),
                    }
                )
        return list(records.values())

    def save_initial_result(self, agent_result: dict[str, Any]) -> dict[str, Any]:
        now = self._now()
        agent_input = agent_result.get("input") or {}
        report = agent_result.get("report") or {}
        score = agent_result.get("final_score") or {}
        record = {
            "task_id": agent_result.get("task_id"),
            "address": agent_input.get("address"),
            "city": agent_input.get("city"),
            "score": score.get("total"),
            "recommendation": score.get("level") or report.get("summary"),
            "agent_report_summary": report.get("summary"),
            "user_feedback": None,
            "actual_business_result": "unknown",
            "monthly_revenue_range": None,
            "features": self._extract_features(agent_result),
            "created_at": now,
            "updated_at": now,
        }
        self._append_event("agent_run_completed", record["task_id"], {"task_id": record["task_id"], "result": agent_result})
        self._append_event("feedback_initialized", record["task_id"], record)
        return record

    def update_feedback(
        self,
        task_id: str,
        *,
        actual_result: str,
        notes: str | None = None,
        monthly_revenue_range: str | None = None,
    ) -> dict[str, Any]:
        actual = str(actual_result or "unknown").strip()
        if actual not in {"profit", "loss", "unknown"}:
            raise ValueError("actual_result must be one of: profit, loss, unknown")

        now = self._now()
        payload = {
            "user_feedback": notes or "",
            "actual_business_result": actual,
            "monthly_revenue_range": monthly_revenue_range,
            "updated_at": now,
        }
        self._append_event("feedback_updated", task_id, payload)
        return self.get_record(task_id) or {"task_id": task_id, **payload}

    def get_record(self, task_id: str) -> dict[str, Any] | None:
        return next((row for row in self.list_records() if row.get("task_id") == task_id), None)

    def events_for_task(self, task_id: str) -> list[dict[str, Any]]:
        return [event for event in self.list_events() if event.get("task_id") == task_id]

    def find_similar_cases(self, current: dict[str, Any], limit: int = 5) -> list[dict[str, Any]]:
        current_features = self._extract_features(current)
        current_task_id = current.get("task_id")
        candidates = []
        for row in self.list_records():
            if row.get("task_id") == current_task_id:
                continue
            similarity, differences = self._similarity(current_features, row.get("features") or {})
            candidates.append(
                {
                    "task_id": row.get("task_id"),
                    "address": row.get("address"),
                    "score": row.get("score"),
                    "recommendation": row.get("recommendation"),
                    "similarity": round(similarity, 3),
                    "historical_result": row.get("actual_business_result") or "unknown",
                    "key_differences": differences,
                }
            )
        candidates.sort(key=lambda item: item["similarity"], reverse=True)
        return candidates[:limit]

    def _append_event(self, event_type: str, task_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        event = {
            "event_type": event_type,
            "task_id": task_id,
            "payload": payload,
            "timestamp": self._now(),
        }
        try:
            with self._lock:
                events = self.list_events()
                events.append(event)
                self._write_events(events)
        except Exception as exc:
            event["feedback_write_error"] = f"{type(exc).__name__}: {exc}"
        return event

    def _write_events(self, events: list[dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps({"events": events}, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        tmp.replace(self.path)

    def can_write(self) -> tuple[bool, str | None]:
        try:
            with self._lock:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                if not self.path.exists():
                    self._write_events([])
                events = self.list_events()
                self._write_events(events)
            return True, None
        except Exception as exc:
            return False, f"{type(exc).__name__}: {exc}"

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _extract_features(agent_result: dict[str, Any]) -> dict[str, Any]:
        agent_input = agent_result.get("input") or {}
        state = agent_result.get("agent_state") or {}
        report = agent_result.get("report") or {}
        score = agent_result.get("final_score") or {}
        geo = state.get("geo") or {}
        poi = state.get("poi") or []
        competitors = state.get("competitor") or []
        redline = state.get("redline") or {}
        return {
            "city": agent_input.get("city"),
            "business_type": agent_input.get("business_type"),
            "longitude": geo.get("longitude") or (geo.get("location") or {}).get("longitude"),
            "latitude": geo.get("latitude") or (geo.get("location") or {}).get("latitude"),
            "score": score.get("total"),
            "competitor_count": len(competitors) if isinstance(competitors, list) else 0,
            "poi_count": len(poi) if isinstance(poi, list) else 0,
            "redline_risk_level": redline.get("risk_level"),
            "confidence": report.get("confidence"),
        }

    @staticmethod
    def _similarity(current: dict[str, Any], past: dict[str, Any]) -> tuple[float, list[str]]:
        score = 0.0
        total = 0.0
        differences = []

        def add_weight(weight: float, matched: bool, diff: str | None = None):
            nonlocal score, total
            total += weight
            if matched:
                score += weight
            elif diff:
                differences.append(diff)

        add_weight(0.2, current.get("city") == past.get("city"), "城市不同")
        add_weight(0.15, current.get("business_type") == past.get("business_type"), "业态不同")
        add_weight(0.2, SiteFeedbackStore._num_close(current.get("score"), past.get("score"), 15), "综合评分差异较大")
        add_weight(0.15, SiteFeedbackStore._num_close(current.get("competitor_count"), past.get("competitor_count"), 3), "竞品数量差异较大")
        add_weight(0.1, SiteFeedbackStore._num_close(current.get("poi_count"), past.get("poi_count"), 20), "POI 总量差异较大")
        add_weight(0.1, current.get("redline_risk_level") == past.get("redline_risk_level"), "红线风险等级不同")
        add_weight(0.1, SiteFeedbackStore._nearby(current, past), "地理位置较远或坐标缺失")
        return (score / total if total else 0.0), differences[:5]

    @staticmethod
    def _num_close(left: Any, right: Any, tolerance: float) -> bool:
        try:
            return abs(float(left) - float(right)) <= tolerance
        except (TypeError, ValueError):
            return False

    @staticmethod
    def _nearby(current: dict[str, Any], past: dict[str, Any]) -> bool:
        try:
            lng_delta = abs(float(current.get("longitude")) - float(past.get("longitude")))
            lat_delta = abs(float(current.get("latitude")) - float(past.get("latitude")))
        except (TypeError, ValueError):
            return False
        return lng_delta <= 0.05 and lat_delta <= 0.05
