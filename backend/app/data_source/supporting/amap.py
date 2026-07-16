from __future__ import annotations

from dataclasses import replace
from typing import Any

from app.data_model.schemas import EntertainmentData, FoodBusinessData, POIData
from app.data_source.amap import AmapProvider
from app.data_source.base import (
    DataSourceName,
    DataSourceRequest,
    ProviderAvailability,
    ProviderCallStatus,
    ProviderResult,
)

from .base import SupportingProvider


FOOD_KEYWORDS = ["餐厅", "小吃", "快餐", "烧烤"]
ENTERTAINMENT_KEYWORDS = ["KTV", "酒吧", "台球", "密室", "电影院"]
NIGHT_ECONOMY_KEYWORDS = ["夜市", "便利店", "超市"]

ENTERTAINMENT_TYPE_MAP = {
    "ktv": "ktv",
    "酒吧": "bar",
    "台球": "billiard",
    "电影院": "cinema",
    "影院": "cinema",
    "密室": "escape_room",
}


def _raw_with_group(poi: POIData, group: str) -> dict[str, Any]:
    raw = dict(poi.raw_data or {})
    raw.setdefault("address", poi.address)
    raw.setdefault("sub_category", poi.sub_category)
    raw["supporting_group"] = group
    return raw


def _entertainment_type(poi: POIData) -> str:
    text = f"{poi.sub_category or ''} {poi.name}".lower()
    for keyword, value in ENTERTAINMENT_TYPE_MAP.items():
        if keyword in text:
            return value
    return "other"


class AmapSupportingProvider(SupportingProvider):
    name = "amap_supporting"
    source = DataSourceName.amap
    display_name = "高德周边配套"
    description = "通过高德周边搜索获取餐饮、娱乐和夜间商业候选数据。"
    check_supported = True

    def __init__(self, poi_provider: AmapProvider | None = None):
        self.poi_provider = poi_provider or AmapProvider()

    @property
    def availability(self) -> ProviderAvailability:
        return self.poi_provider.availability

    async def check_connectivity(self):
        return await self.poi_provider.check_connectivity()

    async def _get_pois(
        self,
        request: DataSourceRequest,
        *,
        category: str,
        keywords: list[str],
    ) -> ProviderResult[POIData]:
        return await self.poi_provider.get_poi(
            replace(request, categories=[category], keywords=list(keywords))
        )

    async def get_food(self, request: DataSourceRequest) -> ProviderResult[FoodBusinessData]:
        result = await self._get_pois(request, category="food", keywords=FOOD_KEYWORDS)
        if result.status == ProviderCallStatus.failed:
            return ProviderResult(self.source, result.status, warnings=result.warnings, metadata=result.metadata)
        items = [
            FoodBusinessData(
                name=poi.name,
                distance_meters=poi.distance_meters,
                category=poi.sub_category or "餐饮",
                business_hours=poi.business_hours,
                source="amap",
                confidence=0.9,
                raw_data=_raw_with_group(poi, "food"),
            )
            for poi in result.items
            if str(poi.category) == "food"
        ]
        return ProviderResult(self.source, result.status, items, result.warnings, result.metadata)

    async def get_entertainment(self, request: DataSourceRequest) -> ProviderResult[EntertainmentData]:
        result = await self._get_pois(request, category="entertainment", keywords=ENTERTAINMENT_KEYWORDS)
        if result.status == ProviderCallStatus.failed:
            return ProviderResult(self.source, result.status, warnings=result.warnings, metadata=result.metadata)
        items = [
            EntertainmentData(
                name=poi.name,
                type=_entertainment_type(poi),
                distance_meters=poi.distance_meters,
                business_hours=poi.business_hours,
                source="amap",
                confidence=0.9,
                raw_data=_raw_with_group(poi, "entertainment"),
            )
            for poi in result.items
            if str(poi.category) == "entertainment"
        ]
        return ProviderResult(self.source, result.status, items, result.warnings, result.metadata)

    async def get_night_economy(self, request: DataSourceRequest) -> ProviderResult[FoodBusinessData]:
        result = await self._get_pois(request, category="food", keywords=NIGHT_ECONOMY_KEYWORDS)
        if result.status == ProviderCallStatus.failed:
            return ProviderResult(self.source, result.status, warnings=result.warnings, metadata=result.metadata)
        items = [
            FoodBusinessData(
                name=poi.name,
                distance_meters=poi.distance_meters,
                category=poi.sub_category or "夜间商业候选",
                business_hours=poi.business_hours,
                # 只有高德明确返回营业时间时才可进一步核实，关键词命中本身不等于夜间营业。
                night_business=True if "夜市" in f"{poi.sub_category or ''}{poi.name}" else None,
                source="amap",
                confidence=0.9,
                raw_data=_raw_with_group(poi, "night_economy"),
            )
            for poi in result.items
            if str(poi.category) == "food"
        ]
        return ProviderResult(self.source, result.status, items, result.warnings, result.metadata)
