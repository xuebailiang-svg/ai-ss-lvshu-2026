from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class AIAnalysisInput(BaseModel):
    project: dict[str, Any]
    location: dict[str, Any]
    environment: dict[str, Any]
    competitors: list[dict[str, Any]]
    competitor_analysis: dict[str, Any] = Field(default_factory=dict)
    supporting_analysis: dict[str, Any] = Field(default_factory=dict)
    rent_analysis: dict[str, Any] = Field(default_factory=dict)
    # 兼容既有输入结构；租金成本分析必须使用 rent_analysis。
    rent: dict[str, Any]
    score_result: dict[str, Any]
    data_quality: dict[str, Any]
    simulation_data_summary: dict[str, Any] = Field(default_factory=dict)
    memory_context: list[dict[str, Any]] = Field(default_factory=list)
    risks: list[Any] = Field(default_factory=list)


class AIReportResponse(BaseModel):
    success: bool = True
    report_id: str | None = None
    content: str | None = None
    model: str | None = None
    created_at: Any | None = None
    message: str | None = None


class AIReviewResponse(BaseModel):
    success: bool = True
    content: str | None = None
    model: str | None = None
    reviewed_at: Any | None = None
    data_quality: dict[str, Any] | None = None
    message: str | None = None


class DeepSeekResult(BaseModel):
    content: str
    model: str
    duration_ms: int
    input_length: int
    output_length: int
