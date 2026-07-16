from __future__ import annotations

from typing import Any, TypeVar

from pydantic import ValidationError

from app.data_model.converters import normalize_data
from app.data_model.schemas import (
    CompetitorData,
    EntertainmentData,
    FoodBusinessData,
    POIData,
    RentData,
)

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


ModelType = TypeVar("ModelType", POIData, CompetitorData, FoodBusinessData, EntertainmentData, RentData)


class ManualUploadProvider(DataProvider):
    """对现有统一转换器的人工上传数据适配器。"""

    name = "manual"
    source = DataSourceName.manual
    display_name = "人工上传"
    description = "支持通过 CSV 补充竞品、餐饮、娱乐、租金和 POI 数据。"
    capabilities = ("poi", "competitor", "food", "entertainment", "rent")
    check_supported = True

    @property
    def availability(self) -> ProviderAvailability:
        return ProviderAvailability.available

    async def check_connectivity(self) -> ConnectivityResult:
        return ConnectivityResult(
            configured=True,
            reachable=True,
            status=ConnectivityStatus.ok,
            message="人工上传为本地能力，无需外部连通性检查",
        )

    def _convert(
        self,
        request: DataSourceRequest,
        data_type: str,
        model: type[ModelType],
    ) -> ProviderResult[ModelType]:
        items: list[ModelType] = []
        warnings: list[str] = []
        for index, raw in enumerate(request.records, start=1):
            payload = {**raw, "source": "manual"}
            try:
                normalized, row_warnings = normalize_data({"type": data_type, "data": payload})
                items.append(model(**normalized))
                warnings.extend(f"第 {index} 条：{warning}" for warning in row_warnings)
            except (ValidationError, ValueError, TypeError) as exc:
                warnings.append(f"第 {index} 条转换失败：{exc}")

        if not request.records:
            status = ProviderCallStatus.success
        elif not items:
            status = ProviderCallStatus.failed
        elif len(items) < len(request.records):
            status = ProviderCallStatus.partial
        else:
            status = ProviderCallStatus.success
        return ProviderResult(provider=self.source, status=status, items=items, warnings=warnings)

    async def get_poi(self, request: DataSourceRequest) -> ProviderResult[POIData]:
        return self._convert(request, "poi", POIData)

    async def get_competitors(self, request: DataSourceRequest) -> ProviderResult[CompetitorData]:
        return self._convert(request, "competitor", CompetitorData)

    async def get_food(self, request: DataSourceRequest) -> ProviderResult[FoodBusinessData]:
        return self._convert(request, "food", FoodBusinessData)

    async def get_entertainment(self, request: DataSourceRequest) -> ProviderResult[EntertainmentData]:
        return self._convert(request, "entertainment", EntertainmentData)

    async def get_rent(self, request: DataSourceRequest) -> ProviderResult[RentData]:
        return self._convert(request, "rent", RentData)
