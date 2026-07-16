from __future__ import annotations

from pydantic import BaseModel, Field


class DataSourceStatusItem(BaseModel):
    name: str
    display_name: str
    status: str
    description: str
    capabilities: list[str] = Field(default_factory=list)
    check_supported: bool = False


class DataSourceStatusResponse(BaseModel):
    items: list[DataSourceStatusItem] = Field(default_factory=list)


class ConnectivityCheckResponse(BaseModel):
    name: str
    configured: bool
    reachable: bool
    status: str
    message: str
    latency_ms: int
    checked_at: str
