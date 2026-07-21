from __future__ import annotations

from pydantic import BaseModel, Field


class ScoringFactorConfig(BaseModel):
    key: str = Field(..., min_length=1, max_length=120)
    name: str = Field(..., min_length=1, max_length=120)
    description: str | None = None
    weight: float = Field(default=0, ge=0)
    enabled: bool = True
    data_sources: list[str] = Field(default_factory=list)
    sort_order: int = 0
    config: dict = Field(default_factory=dict)


class ScoringDimensionConfig(BaseModel):
    key: str = Field(..., min_length=1, max_length=80)
    name: str = Field(..., min_length=1, max_length=120)
    description: str | None = None
    weight: float = Field(default=0, ge=0)
    enabled: bool = True
    data_sources: list[str] = Field(default_factory=list)
    sort_order: int = 0
    factors: list[ScoringFactorConfig] = Field(default_factory=list)


class ScoringConfigResponse(BaseModel):
    dimensions: list[ScoringDimensionConfig]
    total_weight: float
    normalized: bool


class ScoringConfigUpdate(BaseModel):
    dimensions: list[ScoringDimensionConfig]
