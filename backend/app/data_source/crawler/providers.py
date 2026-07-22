from __future__ import annotations

from .base import CrawlerProvider


class CrawlerCompetitorProvider(CrawlerProvider):
    name = "crawler_competitor"
    display_name = "爬虫竞品数据"
    description = "从允许访问的公开网页补充竞品经营信息，结果默认待人工确认。"
    capabilities = ("competitor",)


class CrawlerSupportingProvider(CrawlerProvider):
    name = "crawler_supporting"
    display_name = "爬虫周边配套数据"
    description = "从允许访问的公开网页补充餐饮、娱乐和夜间商业营业信息，结果默认待人工确认。"
    capabilities = ("food", "entertainment", "night_economy")


class CrawlerRentProvider(CrawlerProvider):
    name = "crawler_rent"
    display_name = "爬虫租金数据"
    description = "从允许访问的公开网页补充租金样本，结果默认待人工确认。"
    capabilities = ("rent",)
