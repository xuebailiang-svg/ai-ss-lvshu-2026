from __future__ import annotations

from dataclasses import is_dataclass
from typing import Any

from app.tools.base import ToolResult


class ToolOutputValidator:
    allowed_status = {"success", "failed", "partial"}

    @classmethod
    def validate(cls, output: Any, *, fallback_tool_name: str = "unknown_tool") -> ToolResult:
        warnings: list[str] = []

        if isinstance(output, ToolResult):
            payload = output.to_dict()
        elif isinstance(output, dict):
            payload = dict(output)
            warnings.append("Tool output was dict and normalized by validator.")
        elif is_dataclass(output) and hasattr(output, "__dict__"):
            payload = dict(output.__dict__)
            warnings.append("Tool output dataclass was normalized by validator.")
        else:
            payload = {
                "tool_name": fallback_tool_name,
                "status": "failed",
                "summary": f"Invalid tool output type: {type(output).__name__}",
                "data": {"raw_type": type(output).__name__},
                "confidence": 0,
                "sources": [],
                "warnings": ["Tool output validator converted invalid output to failed ToolResult."],
            }

        tool_name = str(payload.get("tool_name") or fallback_tool_name)
        status = str(payload.get("status") or "failed")
        if status == "skipped":
            status = "partial"
            warnings.append("Tool status 'skipped' was normalized to 'partial'.")
        if status not in cls.allowed_status:
            warnings.append(f"Invalid tool status '{status}' was normalized to 'failed'.")
            status = "failed"

        confidence = cls._confidence(payload.get("confidence"), warnings)
        sources = payload.get("sources")
        if not isinstance(sources, list):
            sources = [] if sources in (None, "") else [str(sources)]
            warnings.append("Tool sources was normalized to list.")
        tool_warnings = payload.get("warnings")
        if not isinstance(tool_warnings, list):
            tool_warnings = [] if tool_warnings in (None, "") else [str(tool_warnings)]
            warnings.append("Tool warnings was normalized to list.")
        data = payload.get("data")
        if not isinstance(data, dict):
            data = {"value": data}
            warnings.append("Tool data was normalized to dict.")

        summary = str(payload.get("summary") or "Tool did not provide summary.")
        if not payload.get("summary"):
            warnings.append("Tool summary was missing and filled by validator.")

        return ToolResult(
            tool_name=tool_name,
            status=status,
            summary=summary,
            data=data,
            confidence=confidence,
            sources=sources,
            warnings=[*tool_warnings, *warnings],
        )

    @staticmethod
    def _confidence(value: Any, warnings: list[str]) -> float:
        try:
            confidence = float(value)
        except (TypeError, ValueError):
            warnings.append("Tool confidence was missing or invalid and normalized to 0.")
            return 0.0
        if confidence < 0 or confidence > 1:
            warnings.append("Tool confidence was clamped to 0~1.")
            confidence = max(0.0, min(1.0, confidence))
        return confidence
