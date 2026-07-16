from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Generic, TypeVar

from app.data_model.schemas import (
    CompetitorData,
    EntertainmentData,
    FoodBusinessData,
    POIData,
    RentData,
)


class DataSourceName(str, Enum):
    amap = "amap"
    manual = "manual"
    crawler = "crawler"
    third_party = "third_party"


class ProviderAvailability(str, Enum):
    available = "available"
    disabled = "disabled"
    not_configured = "not_configured"


class ProviderCallStatus(str, Enum):
    success = "success"
    partial = "partial"
    failed = "failed"
    unsupported = "unsupported"


class ConnectivityStatus(str, Enum):
    ok = "ok"
    failed = "failed"
    not_configured = "not_configured"
    disabled = "disabled"
    unsupported = "unsupported"


@dataclass(slots=True)
class DataSourceRequest:
    project_id: str | None = None
    city: str | None = None
    longitude: float | None = None
    latitude: float | None = None
    radius_meters: int = 1000
    records: list[dict[str, Any]] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)


DataItem = TypeVar(
    "DataItem",
    POIData,
    CompetitorData,
    FoodBusinessData,
    EntertainmentData,
    RentData,
)


@dataclass(slots=True)
class ProviderResult(Generic[DataItem]):
    provider: DataSourceName
    status: ProviderCallStatus
    items: list[DataItem] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ProviderDescriptor:
    name: str
    source: DataSourceName
    display_name: str
    availability: ProviderAvailability
    description: str
    capabilities: tuple[str, ...]
    check_supported: bool


@dataclass(frozen=True, slots=True)
class ConnectivityResult:
    configured: bool
    reachable: bool
    status: ConnectivityStatus
    message: str


class DataProvider:
    """所有外部数据源适配器的统一接口。

    Provider 只负责采集并转换为 ``app.data_model`` 中的统一模型；数据库
    持久化仍由现有 service 层负责。
    """

    name: str
    source: DataSourceName
    display_name: str
    description: str = ""
    capabilities: tuple[str, ...] = ()
    check_supported: bool = False

    @property
    def availability(self) -> ProviderAvailability:
        raise NotImplementedError

    def descriptor(self) -> ProviderDescriptor:
        return ProviderDescriptor(
            name=self.name,
            source=self.source,
            display_name=self.display_name,
            availability=self.availability,
            description=self.description,
            capabilities=self.capabilities,
            check_supported=self.check_supported,
        )

    async def check_connectivity(self) -> ConnectivityResult:
        if self.availability == ProviderAvailability.disabled:
            return ConnectivityResult(False, False, ConnectivityStatus.disabled, f"{self.display_name}当前已禁用")
        if self.availability == ProviderAvailability.not_configured:
            return ConnectivityResult(
                False,
                False,
                ConnectivityStatus.not_configured,
                f"{self.display_name}尚未配置",
            )
        return ConnectivityResult(
            True,
            False,
            ConnectivityStatus.unsupported,
            f"{self.display_name}不支持连通性检查",
        )

    async def get_poi(self, request: DataSourceRequest) -> ProviderResult[POIData]:
        return self._unsupported()

    async def get_competitors(self, request: DataSourceRequest) -> ProviderResult[CompetitorData]:
        return self._unsupported()

    async def get_food(self, request: DataSourceRequest) -> ProviderResult[FoodBusinessData]:
        return self._unsupported()

    async def get_entertainment(self, request: DataSourceRequest) -> ProviderResult[EntertainmentData]:
        return self._unsupported()

    async def get_rent(self, request: DataSourceRequest) -> ProviderResult[RentData]:
        return self._unsupported()

    def _unsupported(self) -> ProviderResult[Any]:
        return ProviderResult(
            provider=self.source,
            status=ProviderCallStatus.unsupported,
            warnings=[f"{self.display_name}暂不支持该数据类型"],
        )
