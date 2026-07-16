from __future__ import annotations

from app.data_model.schemas import RentData
from app.data_source.base import (
    ConnectivityResult,
    ConnectivityStatus,
    DataSourceName,
    DataSourceRequest,
    ProviderAvailability,
    ProviderResult,
)
from app.data_source.manual_upload import ManualUploadProvider

from .base import RentProvider


class ManualRentProvider(RentProvider):
    name = "manual_rent"
    source = DataSourceName.manual
    display_name = "人工租金数据"
    description = "通过 CSV 导入候选物业的真实租金与成本数据。"
    capabilities = ("rent",)
    check_supported = True

    def __init__(self, upload_provider: ManualUploadProvider | None = None):
        self.upload_provider = upload_provider or ManualUploadProvider()

    @property
    def availability(self) -> ProviderAvailability:
        return ProviderAvailability.available

    async def check_connectivity(self) -> ConnectivityResult:
        return ConnectivityResult(
            configured=True,
            reachable=True,
            status=ConnectivityStatus.ok,
            message="人工租金导入为本地能力，无需外部连通性检查",
        )

    async def get_rent(self, request: DataSourceRequest) -> ProviderResult[RentData]:
        return await self.upload_provider.get_rent(request)
