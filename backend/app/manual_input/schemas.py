from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


ManualInputType = Literal["competitor", "rent", "population", "supplement"]


class ManualInputRequest(BaseModel):
    type: ManualInputType
    target_id: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)


class MissingDataItem(BaseModel):
    type: str
    field: str
    description: str


class MissingDataResponse(BaseModel):
    project_id: str
    missing: list[MissingDataItem]


class ManualInputResponse(BaseModel):
    success: bool
    message: str
    updated: dict[str, Any] = Field(default_factory=dict)


class ManualInputsResponse(BaseModel):
    project_id: str
    items: list[dict[str, Any]]
