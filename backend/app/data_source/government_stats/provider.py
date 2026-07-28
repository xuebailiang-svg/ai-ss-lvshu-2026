from __future__ import annotations

import asyncio
import httpx

from app.core.config import get_settings
from app.data_model import RegionalStatisticData
from app.data_source.base import (
    ConnectivityResult,
    ConnectivityStatus,
    DataProvider,
    DataSourceName,
    DataSourceRequest,
    ProviderAvailability,
    ProviderCallStatus,
    ProviderResult,
)
from app.system_config.service import resolve_config_value

from .adapters import ADAPTERS, SOURCES


class GovernmentStatsProvider(DataProvider):
    name = "government_stats"
    source = DataSourceName.government_stats
    display_name = "政府公开数据"
    description = "国家、陕西省和西安市统计公报与年度公开指标，仅作为城市或行政区宏观背景。"
    capabilities = ("regional_statistics", "population", "economy", "consumption", "employment")
    check_supported = True

    @property
    def availability(self) -> ProviderAvailability:
        settings = get_settings()
        enabled = resolve_config_value(
            "gov_data_enabled",
            "true" if settings.gov_data_enabled else "false",
        ).strip().lower() in {"1", "true", "yes", "on"}
        return ProviderAvailability.available if enabled else ProviderAvailability.disabled

    def _source_keys(self, request: DataSourceRequest | None = None) -> list[str]:
        settings = get_settings()
        configured_value = resolve_config_value("gov_data_sources", settings.gov_data_sources)
        configured = [item.strip() for item in configured_value.split(",") if item.strip()]
        requested = request.categories if request and request.categories else configured
        return [item for item in requested if item in SOURCES]

    async def _with_retries(self, operation):
        settings = get_settings()
        retries = max(
            0,
            int(resolve_config_value("gov_data_max_retries", str(settings.gov_data_max_retries))),
        )
        delay = max(
            0,
            float(resolve_config_value("gov_data_rate_limit_seconds", str(settings.gov_data_rate_limit_seconds))),
        )
        last_error: Exception | None = None
        for attempt in range(retries + 1):
            try:
                if attempt and delay:
                    await asyncio.sleep(delay)
                return await operation()
            except (httpx.TimeoutException, httpx.RequestError, httpx.HTTPStatusError) as exc:
                last_error = exc
        if last_error is not None:
            raise last_error
        raise RuntimeError("政府公开数据请求未执行")

    async def check_connectivity(self) -> ConnectivityResult:
        if self.availability == ProviderAvailability.disabled:
            return ConnectivityResult(True, False, ConnectivityStatus.disabled, "政府公开数据采集已关闭")
        settings = get_settings()
        timeout_value = resolve_config_value("gov_data_timeout_seconds", str(settings.gov_data_timeout_seconds))
        timeout = httpx.Timeout(float(timeout_value))
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            for key in self._source_keys():
                try:
                    adapter = ADAPTERS[key](client)
                    await self._with_retries(adapter.check)
                    return ConnectivityResult(True, True, ConnectivityStatus.ok, f"{SOURCES[key].source_name}公开页面可访问")
                except (httpx.TimeoutException, httpx.RequestError, httpx.HTTPStatusError):
                    continue
        return ConnectivityResult(True, False, ConnectivityStatus.failed, "政府公开数据页面暂时无法访问")

    async def get_statistics(self, request: DataSourceRequest) -> ProviderResult[RegionalStatisticData]:
        if self.availability == ProviderAvailability.disabled:
            return ProviderResult(
                provider=self.source,
                status=ProviderCallStatus.failed,
                warnings=["政府公开数据采集已关闭"],
            )
        settings = get_settings()
        timeout_value = resolve_config_value("gov_data_timeout_seconds", str(settings.gov_data_timeout_seconds))
        timeout = httpx.Timeout(float(timeout_value))
        items: list[RegionalStatisticData] = []
        warnings: list[str] = []
        source_results: dict[str, dict[str, object]] = {}
        rate_limit = max(
            0,
            float(resolve_config_value("gov_data_rate_limit_seconds", str(settings.gov_data_rate_limit_seconds))),
        )
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": settings.gov_data_user_agent},
        ) as client:
            for source_index, key in enumerate(self._source_keys(request)):
                if source_index and rate_limit:
                    await asyncio.sleep(rate_limit)
                source = SOURCES[key]
                if key == "xian" and request.city and "西安" not in request.city:
                    warnings.append(f"{request.city}尚未配置对应的市级统计适配器")
                    continue
                try:
                    adapter = ADAPTERS[key](client)
                    rows, source_warnings = await self._with_retries(adapter.collect)
                    items.extend(rows)
                    warnings.extend(source_warnings)
                    source_results[key] = {"count": len(rows), "warnings": source_warnings}
                except httpx.TimeoutException:
                    message = f"{source.source_name}访问超时"
                    warnings.append(message)
                    source_results[key] = {"count": 0, "warnings": [message]}
                except (httpx.RequestError, httpx.HTTPStatusError):
                    message = f"{source.source_name}公开页面访问失败"
                    warnings.append(message)
                    source_results[key] = {"count": 0, "warnings": [message]}

        status = ProviderCallStatus.success
        if not items:
            status = ProviderCallStatus.failed
        elif warnings:
            status = ProviderCallStatus.partial
        return ProviderResult(
            provider=self.source,
            status=status,
            items=items,
            warnings=warnings,
            metadata={"sources": source_results},
        )
