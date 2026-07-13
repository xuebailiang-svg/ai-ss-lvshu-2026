from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class DimensionScore(BaseModel):
    score: float
    max: float
    confidence: float
    reasons: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    missing_data: list[str] = Field(default_factory=list)


class ProjectScoreResponse(BaseModel):
    project_id: str
    total_score: float
    level: str
    confidence: float
    dimensions: dict[str, DimensionScore]
    advantages: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    missing_data: list[str] = Field(default_factory=list)
    scoring_version: str
    score_id: int | None = None
    created_at: Any | None = None
