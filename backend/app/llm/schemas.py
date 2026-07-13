from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class AIAnalysisInput(BaseModel):
    project: dict[str, Any]
    location: dict[str, Any]
    environment: dict[str, Any]
    competitors: list[dict[str, Any]]
    rent: dict[str, Any]
    score_result: dict[str, Any]
    data_quality: dict[str, Any]
    risks: list[Any] = Field(default_factory=list)


class AIReportResponse(BaseModel):
    success: bool = True
    report_id: str | None = None
    content: str | None = None
    model: str | None = None
    created_at: Any | None = None
    message: str | None = None


class DeepSeekResult(BaseModel):
    content: str
    model: str
    duration_ms: int
    input_length: int
    output_length: int
