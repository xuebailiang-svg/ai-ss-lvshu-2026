from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.config import get_settings


class AgentTraceStore:
    """Local JSON trace store for Agent replay and debugging."""
    _lock = threading.RLock()

    def __init__(self, path: str | None = None):
        self.path = Path(path or get_settings().agent_trace_store_path)
        if not self.path.is_absolute():
            self.path = Path.cwd() / self.path

    def start_run(self, task_id: str, payload: dict[str, Any]) -> None:
        try:
            with self._lock:
                data = self._read()
                data.setdefault("traces", {})[task_id] = {
                    "task_id": task_id,
                    "input": payload,
                    "trace": [],
                    "created_at": self._now(),
                    "updated_at": self._now(),
                }
                self._write(data)
        except Exception:
            return None

    def append_step(
        self,
        task_id: str,
        *,
        step_name: str,
        input_data: dict[str, Any] | None = None,
        output_data: dict[str, Any] | None = None,
        tool_name: str | None = None,
        status: str | None = None,
        confidence: float | None = None,
        duration_ms: int | float | None = None,
    ) -> dict[str, Any]:
        event = {
            "step_name": step_name,
            "step": step_name,
            "input": input_data or {},
            "output": output_data or {},
            "tool_name": tool_name or step_name,
            "tool": tool_name or step_name,
            "status": status,
            "confidence": confidence,
            "duration_ms": duration_ms or 0,
            "duration": duration_ms or 0,
            "timestamp": self._now(),
        }
        try:
            with self._lock:
                data = self._read()
                run = data.setdefault("traces", {}).setdefault(
                    task_id,
                    {"task_id": task_id, "input": {}, "trace": [], "created_at": self._now()},
                )
                run.setdefault("trace", []).append(event)
                run["updated_at"] = self._now()
                self._write(data)
        except Exception as exc:
            event["trace_write_error"] = f"{type(exc).__name__}: {exc}"
        return event

    def get_trace(self, task_id: str) -> dict[str, Any] | None:
        return self._read().get("traces", {}).get(task_id)

    def summary(self, task_id: str) -> dict[str, Any]:
        trace = (self.get_trace(task_id) or {}).get("trace", [])
        confidences = [float(step.get("confidence")) for step in trace if step.get("confidence") is not None]
        failed = [step for step in trace if step.get("status") == "failed"]
        return {
            "total_steps": len(trace),
            "failed_steps": len(failed),
            "avg_confidence": round(sum(confidences) / len(confidences), 3) if confidences else 0,
            "total_duration_ms": round(sum(float(step.get("duration_ms") or 0) for step in trace), 2),
        }

    def _read(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"traces": {}}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {"traces": {}}
        if isinstance(data, dict) and isinstance(data.get("traces"), dict):
            return data
        return {"traces": {}}

    def _write(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        tmp.replace(self.path)

    def can_write(self) -> tuple[bool, str | None]:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            if not self.path.exists():
                self._write({"traces": {}})
            data = self._read()
            self._write(data)
            return True, None
        except Exception as exc:
            return False, f"{type(exc).__name__}: {exc}"

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()
