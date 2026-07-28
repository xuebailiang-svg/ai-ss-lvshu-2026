from __future__ import annotations

import re
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urljoin

import httpx

from app.data_model import RegionalStatisticData

from .parser import html_to_text, parse_official_text


class LinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "a":
            self._href = dict(attrs).get("href")
            self._text = []

    def handle_data(self, data):
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag):
        if tag.lower() == "a" and self._href is not None:
            self.links.append((self._href, "".join(self._text).strip()))
            self._href = None
            self._text = []


@dataclass(frozen=True)
class OfficialSource:
    key: str
    source_name: str
    index_url: str
    scope_level: str
    scope_code: str
    scope_name: str
    title_pattern: str


SOURCES: dict[str, OfficialSource] = {
    "national": OfficialSource(
        key="national",
        source_name="国家统计局",
        index_url="https://www.stats.gov.cn/sj/tjgb/ndtjgb/qgndtjgb/",
        scope_level="country",
        scope_code="100000",
        scope_name="全国",
        title_pattern=r"(?:中华人民共和国)?20\d{2}年(?:国民经济和社会发展统计公报)?",
    ),
    "shaanxi": OfficialSource(
        key="shaanxi",
        source_name="陕西省统计局",
        index_url="https://tjj.shaanxi.gov.cn/tjsj/",
        scope_level="province",
        scope_code="610000",
        scope_name="陕西省",
        title_pattern=r"20\d{2}年陕西省国民经济和社会发展统计公报",
    ),
    "xian": OfficialSource(
        key="xian",
        source_name="西安市统计局",
        index_url="https://tjj.xa.gov.cn/tjsj/tjgb/1.html",
        scope_level="city",
        scope_code="610100",
        scope_name="西安市",
        title_pattern=r"西安市20\d{2}年国民经济和社会发展统计公报",
    ),
}


class OfficialStatisticsAdapter:
    def __init__(self, source: OfficialSource, client: httpx.AsyncClient):
        self.source = source
        self.client = client

    async def check(self) -> None:
        response = await self.client.get(self.source.index_url)
        response.raise_for_status()

    async def collect(self) -> tuple[list[RegionalStatisticData], list[str]]:
        index_response = await self.client.get(self.source.index_url)
        index_response.raise_for_status()
        parser = LinkParser()
        parser.feed(index_response.text)
        candidates = [
            (urljoin(str(index_response.url), href), title)
            for href, title in parser.links
            if re.search(self.source.title_pattern, re.sub(r"\s+", "", title))
        ]
        if not candidates:
            # 有些统计局首页直接包含完整公报正文。
            items = parse_official_text(
                html_to_text(index_response.text),
                scope_level=self.source.scope_level,
                scope_code=self.source.scope_code,
                scope_name=self.source.scope_name,
                source_name=self.source.source_name,
                source_url=str(index_response.url),
                source_format="html",
            )
            return items, ([] if items else [f"{self.source.source_name}未识别到最新统计公报链接"])

        candidates.sort(key=lambda item: re.findall(r"20\d{2}", item[1]), reverse=True)
        detail_url, title = candidates[0]
        detail_response = await self.client.get(detail_url)
        detail_response.raise_for_status()
        is_pdf = (
            detail_url.lower().endswith(".pdf")
            or "application/pdf" in detail_response.headers.get("content-type", "").lower()
        )
        if is_pdf:
            from .upload import parse_pdf_upload

            items, pdf_errors = parse_pdf_upload(
                detail_response.content,
                scope_level=self.source.scope_level,
                scope_code=self.source.scope_code,
                scope_name=self.source.scope_name,
                source_name=self.source.source_name,
                source_url=str(detail_response.url),
                stat_period=max(re.findall(r"20\d{2}", title), default=""),
            )
            warnings = [item["reason"] for item in pdf_errors]
            return items, warnings
        items = parse_official_text(
            html_to_text(detail_response.text),
            scope_level=self.source.scope_level,
            scope_code=self.source.scope_code,
            scope_name=self.source.scope_name,
            source_name=self.source.source_name,
            source_url=str(detail_response.url),
            source_format="html",
        )
        warnings = [] if items else [f"{self.source.source_name}公报页面可访问，但未识别到目标指标"]
        return items, warnings


class NationalStatsAdapter(OfficialStatisticsAdapter):
    def __init__(self, client: httpx.AsyncClient):
        super().__init__(SOURCES["national"], client)


class ShaanxiStatsAdapter(OfficialStatisticsAdapter):
    def __init__(self, client: httpx.AsyncClient):
        super().__init__(SOURCES["shaanxi"], client)


class XianStatsAdapter(OfficialStatisticsAdapter):
    def __init__(self, client: httpx.AsyncClient):
        super().__init__(SOURCES["xian"], client)


ADAPTERS = {
    "national": NationalStatsAdapter,
    "shaanxi": ShaanxiStatsAdapter,
    "xian": XianStatsAdapter,
}
