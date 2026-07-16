from __future__ import annotations

from app.map_data.amap_client import AmapMapDataClient

from .amap import AmapProvider
from .base import DataProvider, DataSourceName, ProviderAvailability, ProviderDescriptor
from .manual_upload import ManualUploadProvider
from .competitor import AmapCompetitorProvider, CrawlerCompetitorProvider
from .rent import ManualRentProvider
from .supporting import AmapSupportingProvider


class PlaceholderProvider(DataProvider):
    def __init__(
        self,
        source: DataSourceName,
        display_name: str,
        availability: ProviderAvailability,
        description: str,
    ):
        self.name = source.value
        self.source = source
        self.display_name = display_name
        self._availability = availability
        self.description = description
        self.capabilities = ()

    @property
    def availability(self) -> ProviderAvailability:
        return self._availability

    async def check_connectivity(self):
        if self.source == DataSourceName.crawler:
            result = await super().check_connectivity()
            return type(result)(False, False, result.status, "爬虫能力尚未开发")
        result = await super().check_connectivity()
        return type(result)(False, False, result.status, "第三方消费数据尚未配置")


class DataSourceRegistry:
    def __init__(self):
        self._providers: dict[str, DataProvider] = {}

    def register(self, provider: DataProvider) -> None:
        self._providers[provider.name] = provider

    def get(self, name: DataSourceName | str) -> DataProvider:
        key = name.value if isinstance(name, DataSourceName) else str(name)
        return self._providers[key]

    def list(self) -> list[ProviderDescriptor]:
        return [provider.descriptor() for provider in self._providers.values()]


def build_default_registry(*, amap_client: AmapMapDataClient | None = None) -> DataSourceRegistry:
    registry = DataSourceRegistry()
    registry.register(AmapProvider(amap_client))
    registry.register(ManualUploadProvider())
    registry.register(ManualRentProvider())
    registry.register(AmapCompetitorProvider(AmapProvider(amap_client)))
    registry.register(CrawlerCompetitorProvider())
    registry.register(AmapSupportingProvider(AmapProvider(amap_client)))
    registry.register(
        PlaceholderProvider(
            DataSourceName.crawler,
            "爬虫数据",
            ProviderAvailability.disabled,
            "爬虫采集能力尚未开发，当前不可用。",
        )
    )
    registry.register(
        PlaceholderProvider(
            DataSourceName.third_party,
            "第三方消费数据",
            ProviderAvailability.not_configured,
            "第三方消费数据接口尚未接入或配置。",
        )
    )
    return registry
