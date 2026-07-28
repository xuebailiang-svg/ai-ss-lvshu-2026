from __future__ import annotations

from dataclasses import dataclass

from app.core.config import get_settings
from app.data_source.base import (
    ConnectivityResult,
    ConnectivityStatus,
    DataProvider,
    DataSourceName,
    ProviderAvailability,
)
from app.system_config.service import resolve_config_value
from .runtime import read_worker_health


def _truthy(value: str | bool | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _int_config(key: str, default: int) -> int:
    raw = resolve_config_value(key, str(default))
    try:
        return int(str(raw).strip())
    except (TypeError, ValueError):
        return default


def _csv_config(key: str, fallback: str) -> list[str]:
    raw = resolve_config_value(key, fallback)
    return [item.strip().lower() for item in str(raw or "").split(",") if item.strip()]


@dataclass(frozen=True)
class CrawlerSettings:
    enabled: bool
    provider: str
    timeout_seconds: int
    max_pages_per_task: int
    max_tasks_per_project: int
    rate_limit_seconds: int
    allowed_domains: list[str]
    blocked_domains: list[str]
    search_enabled: bool
    search_provider: str
    search_max_results: int
    search_timeout_seconds: int
    search_allowed_domains: list[str]


def crawler_settings() -> CrawlerSettings:
    settings = get_settings()
    return CrawlerSettings(
        enabled=_truthy(resolve_config_value("crawler_enabled", "true" if settings.crawler_enabled else "false")),
        provider=resolve_config_value("crawler_provider", settings.crawler_provider) or "crawl4ai",
        timeout_seconds=_int_config("crawler_timeout_seconds", settings.crawler_timeout_seconds),
        max_pages_per_task=_int_config("crawler_max_pages_per_task", settings.crawler_max_pages_per_task),
        max_tasks_per_project=_int_config("crawler_max_tasks_per_project", settings.crawler_max_tasks_per_project),
        rate_limit_seconds=_int_config("crawler_rate_limit_seconds", settings.crawler_rate_limit_seconds),
        allowed_domains=_csv_config("crawler_allowed_domains", settings.crawler_allowed_domains),
        blocked_domains=_csv_config("crawler_blocked_domains", settings.crawler_blocked_domains),
        search_enabled=_truthy(resolve_config_value("crawler_search_enabled", "true" if settings.crawler_search_enabled else "false")),
        search_provider=resolve_config_value("crawler_search_provider", settings.crawler_search_provider) or "duckduckgo_html",
        search_max_results=_int_config("crawler_search_max_results", settings.crawler_search_max_results),
        search_timeout_seconds=_int_config("crawler_search_timeout_seconds", settings.crawler_search_timeout_seconds),
        search_allowed_domains=_csv_config("crawler_search_allowed_domains", settings.crawler_search_allowed_domains),
    )


class CrawlerProvider(DataProvider):
    source = DataSourceName.crawler
    check_supported = True

    @property
    def availability(self) -> ProviderAvailability:
        if not crawler_settings().enabled:
            return ProviderAvailability.disabled
        return (
            ProviderAvailability.available
            if read_worker_health().get("reachable")
            else ProviderAvailability.not_configured
        )

    async def check_connectivity(self) -> ConnectivityResult:
        settings = crawler_settings()
        if not settings.enabled:
            return ConnectivityResult(False, False, ConnectivityStatus.disabled, "爬虫能力未启用")
        if settings.provider != "crawl4ai":
            return ConnectivityResult(False, False, ConnectivityStatus.not_configured, "当前仅支持 crawl4ai")
        health = read_worker_health()
        if health.get("reachable"):
            return ConnectivityResult(True, True, ConnectivityStatus.ok, "独立爬虫 Worker 和 Chromium 运行正常")
        if health.get("status") == "not_installed":
            return ConnectivityResult(
                True,
                False,
                ConnectivityStatus.not_configured,
                "独立爬虫 Worker 尚未安装，请执行 scripts/crawler/install.sh",
            )
        return ConnectivityResult(
            True,
            False,
            ConnectivityStatus.failed,
            str(health.get("message") or "独立爬虫 Worker 不可用"),
        )
