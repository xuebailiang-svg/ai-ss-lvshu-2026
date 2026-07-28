from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


CrawlTaskType = Literal["competitor", "supporting", "rent"]
CrawlTaskStatus = Literal["pending", "running", "success", "partial", "failed", "skipped"]


class CrawlEnrichRequest(BaseModel):
    types: list[CrawlTaskType] = Field(default_factory=lambda: ["competitor", "supporting", "rent"])
    max_items: int = Field(default=20, ge=1, le=100)
    discover_urls: bool = True


class CrawlManualUrlRequest(BaseModel):
    task_type: CrawlTaskType
    name: str = Field(min_length=1, max_length=200)
    address: str | None = Field(default=None, max_length=300)
    url: str = Field(min_length=8, max_length=2000)
    record_type: Literal["food", "entertainment"] | None = None


class CrawlSavedCounts(BaseModel):
    competitors: int = 0
    supporting: int = 0
    rent: int = 0


class CrawlEnrichResponse(BaseModel):
    success: bool
    project_id: str
    task_count: int
    task_ids: list[int] = Field(default_factory=list)
    completed_count: int
    failed_count: int
    skipped_count: int = 0
    discovered_url_count: int = 0
    saved: CrawlSavedCounts
    message: str


class CrawlTaskItem(BaseModel):
    id: int
    project_id: str
    task_type: str
    target_name: str | None = None
    target_address: str | None = None
    target_url: str | None = None
    provider: str
    status: str
    source_domain: str | None = None
    error_message: str | None = None
    created_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None


class CrawlTaskListResponse(BaseModel):
    items: list[CrawlTaskItem]
    total: int


class CrawlTaskDetailResponse(CrawlTaskItem):
    input_snapshot: dict = Field(default_factory=dict)
    result_snapshot: dict = Field(default_factory=dict)
