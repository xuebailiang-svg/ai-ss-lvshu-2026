from __future__ import annotations

from pydantic import BaseModel, Field


class ConfigItemStatus(BaseModel):
    configured: bool
    source: str
    masked: str | None = None


class SystemConfigStatus(BaseModel):
    management_enabled: bool
    deepseek: ConfigItemStatus
    amap: ConfigItemStatus
    amap_js: ConfigItemStatus
    amap_security: ConfigItemStatus
    third_party: ConfigItemStatus
    crawler: ConfigItemStatus
    deepseek_base_url: str
    deepseek_model: str
    crawler_enabled: bool = False
    crawler_provider: str = "crawl4ai"
    crawler_timeout_seconds: int = 60
    crawler_max_pages_per_task: int = 5
    crawler_max_tasks_per_project: int = 50
    crawler_rate_limit_seconds: int = 5
    crawler_allowed_domains: str = ""
    crawler_blocked_domains: str = ""
    crawler_search_enabled: bool = True
    crawler_search_provider: str = "duckduckgo_html"
    crawler_search_max_results: int = 5
    crawler_search_timeout_seconds: int = 10
    crawler_search_allowed_domains: str = ""
    warnings: list[str] = Field(default_factory=list)


class SystemConfigUpdate(BaseModel):
    deepseek_api_key: str | None = Field(default=None, max_length=512)
    deepseek_base_url: str | None = Field(default=None, max_length=500)
    deepseek_model: str | None = Field(default=None, max_length=200)
    amap_web_service_key: str | None = Field(default=None, max_length=512)
    amap_js_key: str | None = Field(default=None, max_length=512)
    amap_security_js_code: str | None = Field(default=None, max_length=512)
    third_party_api_key: str | None = Field(default=None, max_length=512)
    crawler_enabled: str | None = Field(default=None, max_length=20)
    crawler_provider: str | None = Field(default=None, max_length=80)
    crawler_timeout_seconds: str | None = Field(default=None, max_length=20)
    crawler_max_pages_per_task: str | None = Field(default=None, max_length=20)
    crawler_max_tasks_per_project: str | None = Field(default=None, max_length=20)
    crawler_rate_limit_seconds: str | None = Field(default=None, max_length=20)
    crawler_allowed_domains: str | None = Field(default=None, max_length=1000)
    crawler_blocked_domains: str | None = Field(default=None, max_length=1000)
    crawler_search_enabled: str | None = Field(default=None, max_length=20)
    crawler_search_provider: str | None = Field(default=None, max_length=80)
    crawler_search_max_results: str | None = Field(default=None, max_length=20)
    crawler_search_timeout_seconds: str | None = Field(default=None, max_length=20)
    crawler_search_allowed_domains: str | None = Field(default=None, max_length=1000)


class ConnectionTestResponse(BaseModel):
    success: bool
    provider: str
    message: str
    latency_ms: int | None = None
