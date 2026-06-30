from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class ToolResult:
    tool_name: str
    status: str
    summary: str
    data: dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    sources: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class BaseTool:
    tool_name = "base_tool"

    async def run(self, context: dict[str, Any]) -> ToolResult:
        raise NotImplementedError

    def success(
        self,
        summary: str,
        *,
        data: dict[str, Any] | None = None,
        confidence: float = 0.7,
        sources: list[str] | None = None,
        warnings: list[str] | None = None,
    ) -> ToolResult:
        return ToolResult(
            tool_name=self.tool_name,
            status="success",
            summary=summary,
            data=data or {},
            confidence=confidence,
            sources=sources or [],
            warnings=warnings or [],
        )

    def failed(
        self,
        summary: str,
        *,
        data: dict[str, Any] | None = None,
        confidence: float = 0.0,
        sources: list[str] | None = None,
        warnings: list[str] | None = None,
    ) -> ToolResult:
        return ToolResult(
            tool_name=self.tool_name,
            status="failed",
            summary=summary,
            data=data or {},
            confidence=confidence,
            sources=sources or [],
            warnings=warnings or [],
        )
