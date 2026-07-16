from __future__ import annotations

import httpx

from app.data_model.schemas import POIData
from app.map_data.amap_client import AmapConfigError, AmapMapDataClient
from app.map_data.mapper import amap_poi_to_unified

from .base import (
    DataProvider,
    DataSourceName,
    DataSourceRequest,
    ConnectivityResult,
    ConnectivityStatus,
    ProviderAvailability,
    ProviderCallStatus,
    ProviderResult,
)


class AmapProvider(DataProvider):
    """对现有 ``AmapMapDataClient`` 的轻量适配器。"""

    name = "amap"
    source = DataSourceName.amap
    display_name = "高德地图"
    description = "提供项目周边 POI、交通、竞品、餐饮和娱乐等基础位置数据。"
    capabilities = ("poi",)
    check_supported = True

    def __init__(self, client: AmapMapDataClient | None = None):
        self.client = client or AmapMapDataClient()

    @property
    def availability(self) -> ProviderAvailability:
        if self.client.mock or bool(self.client.key):
            return ProviderAvailability.available
        return ProviderAvailability.not_configured

    async def check_connectivity(self) -> ConnectivityResult:
        if self.availability == ProviderAvailability.not_configured:
            return ConnectivityResult(
                configured=False,
                reachable=False,
                status=ConnectivityStatus.not_configured,
                message="AMAP_WEB_SERVICE_KEY未配置",
            )
        try:
            data = await self.client.check_connectivity(timeout_seconds=3.0)
        except httpx.TimeoutException:
            return ConnectivityResult(True, False, ConnectivityStatus.failed, "高德接口连接超时")
        except (httpx.RequestError, httpx.HTTPStatusError):
            return ConnectivityResult(True, False, ConnectivityStatus.failed, "服务器无法访问高德接口")
        except Exception:  # 不向调用方返回可能包含 Key 或 URL 的底层异常
            return ConnectivityResult(True, False, ConnectivityStatus.failed, "高德接口连通性检查失败")

        if data.get("status") == "1" and str(data.get("infocode")) == "10000":
            return ConnectivityResult(True, True, ConnectivityStatus.ok, "高德接口连通正常")

        info = str(data.get("info") or "")
        infocode = str(data.get("infocode") or "")
        if info in {"INVALID_USER_KEY", "USERKEY_PLAT_NOMATCH", "INVALID_USER_SCODE"} or infocode in {
            "10001",
            "10002",
            "10007",
        }:
            message = "高德接口返回 Key 错误或权限不足"
        elif infocode == "10021" or info == "CUQPS_HAS_EXCEEDED_THE_LIMIT":
            message = "高德接口当前限流，请稍后重试"
        else:
            message = "高德接口返回异常"
        return ConnectivityResult(True, False, ConnectivityStatus.failed, message)

    async def get_poi(self, request: DataSourceRequest) -> ProviderResult[POIData]:
        if request.longitude is None or request.latitude is None:
            return ProviderResult(
                provider=self.source,
                status=ProviderCallStatus.failed,
                warnings=["缺少经纬度，无法调用高德周边 POI。"],
            )
        try:
            rows, diagnostics = await self.client.collect_pois(
                longitude=request.longitude,
                latitude=request.latitude,
                radius_meters=request.radius_meters,
                city=request.city,
                category_keywords=(
                    {
                        category: request.keywords
                        for category in (request.categories or ["other"])
                    }
                    if request.keywords
                    else None
                ),
            )
        except AmapConfigError as exc:
            return ProviderResult(
                provider=self.source,
                status=ProviderCallStatus.failed,
                warnings=[str(exc)],
            )

        items = [
            POIData(**amap_poi_to_unified(
                row,
                category=row.get("category"),
                sub_category=row.get("sub_category"),
            ))
            for row in rows
        ]
        failed_keywords = diagnostics.get("failed_keywords", [])
        return ProviderResult(
            provider=self.source,
            status=ProviderCallStatus.partial if failed_keywords else ProviderCallStatus.success,
            items=items,
            warnings=[f"{len(failed_keywords)} 个关键词采集失败"] if failed_keywords else [],
            metadata={"diagnostics": diagnostics},
        )
