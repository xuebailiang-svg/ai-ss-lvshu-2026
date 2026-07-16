from __future__ import annotations

from app.data_model.schemas import FoodBusinessData
from app.data_source.base import DataProvider, DataSourceRequest, ProviderResult


class SupportingProvider(DataProvider):
    """周边配套采集 Provider 的统一接口。"""

    capabilities = ("food", "entertainment", "night_economy")

    async def get_night_economy(self, request: DataSourceRequest) -> ProviderResult[FoodBusinessData]:
        return self._unsupported()
