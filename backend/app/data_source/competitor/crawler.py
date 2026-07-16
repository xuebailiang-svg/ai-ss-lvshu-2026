from __future__ import annotations

from app.data_source.base import DataSourceName, ProviderAvailability

from .base import CompetitorProvider


class CrawlerCompetitorProvider(CompetitorProvider):
    name = "crawler_competitor"
    source = DataSourceName.crawler
    display_name = "爬虫竞品数据"
    description = "竞品爬虫能力尚未开发，当前仅保留扩展位置。"
    check_supported = False

    @property
    def availability(self) -> ProviderAvailability:
        return ProviderAvailability.disabled
