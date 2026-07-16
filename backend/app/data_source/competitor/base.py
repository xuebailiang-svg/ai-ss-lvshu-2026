from __future__ import annotations

from app.data_source.base import DataProvider


class CompetitorProvider(DataProvider):
    """竞品采集 Provider 的统一类型标记。"""

    capabilities = ("competitor",)
