from __future__ import annotations

from app.data_model.schemas import RentData
from app.data_source.base import DataProvider, DataSourceRequest, ProviderResult


class RentProvider(DataProvider):
    """租金数据 Provider 的统一接口。"""

    capabilities = ("rent",)

    async def get_rent(self, request: DataSourceRequest) -> ProviderResult[RentData]:
        return self._unsupported()
