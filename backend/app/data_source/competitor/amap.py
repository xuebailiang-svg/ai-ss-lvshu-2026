from __future__ import annotations

from dataclasses import replace

from app.data_model.enums import DataStatus
from app.data_model.schemas import CompetitorData
from app.data_source.amap import AmapProvider
from app.data_source.base import (
    DataSourceName,
    DataSourceRequest,
    ProviderAvailability,
    ProviderCallStatus,
    ProviderResult,
)

from .base import CompetitorProvider


AMAP_COMPETITOR_KEYWORDS = ["电竞馆", "网吧", "网咖", "互联网服务"]


class AmapCompetitorProvider(CompetitorProvider):
    name = "amap_competitor"
    source = DataSourceName.amap
    display_name = "高德竞品数据"
    description = "通过高德周边搜索获取电竞馆、网吧、网咖等基础竞品信息。"
    check_supported = True

    def __init__(self, poi_provider: AmapProvider | None = None):
        self.poi_provider = poi_provider or AmapProvider()

    @property
    def availability(self) -> ProviderAvailability:
        return self.poi_provider.availability

    async def check_connectivity(self):
        return await self.poi_provider.check_connectivity()

    async def get_competitors(self, request: DataSourceRequest) -> ProviderResult[CompetitorData]:
        poi_request = replace(
            request,
            categories=["competitor"],
            keywords=list(AMAP_COMPETITOR_KEYWORDS),
        )
        poi_result = await self.poi_provider.get_poi(poi_request)
        if poi_result.status == ProviderCallStatus.failed:
            return ProviderResult(
                provider=self.source,
                status=ProviderCallStatus.failed,
                warnings=poi_result.warnings,
                metadata=poi_result.metadata,
            )

        items: list[CompetitorData] = []
        seen: set[tuple[str, str | None]] = set()
        for poi in poi_result.items:
            if str(poi.category) != "competitor":
                continue
            identity = (poi.name.strip(), poi.address)
            if identity in seen:
                continue
            seen.add(identity)
            items.append(
                CompetitorData(
                    name=poi.name,
                    address=poi.address,
                    distance_meters=poi.distance_meters,
                    source="amap",
                    status=DataStatus.pending_review,
                    confidence=0.9,
                    raw_data=poi.raw_data,
                )
            )
        return ProviderResult(
            provider=self.source,
            status=poi_result.status,
            items=items,
            warnings=poi_result.warnings,
            metadata=poi_result.metadata,
        )
