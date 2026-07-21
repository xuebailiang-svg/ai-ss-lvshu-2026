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
    deepseek_base_url: str
    deepseek_model: str
    warnings: list[str] = Field(default_factory=list)


class SystemConfigUpdate(BaseModel):
    deepseek_api_key: str | None = Field(default=None, max_length=512)
    deepseek_base_url: str | None = Field(default=None, max_length=500)
    deepseek_model: str | None = Field(default=None, max_length=200)
    amap_web_service_key: str | None = Field(default=None, max_length=512)
    amap_js_key: str | None = Field(default=None, max_length=512)
    amap_security_js_code: str | None = Field(default=None, max_length=512)
    third_party_api_key: str | None = Field(default=None, max_length=512)


class ConnectionTestResponse(BaseModel):
    success: bool
    provider: str
    message: str
    latency_ms: int | None = None
